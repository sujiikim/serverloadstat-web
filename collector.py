#!/usr/bin/env python3
import argparse
import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

DATA_FILE = "data/stat_data.json"
INTERVAL = 3.0
SSH_CONNECT_TIMEOUT = 2
SSH_CMD_TIMEOUT = 6
TOP_USERS_LIMIT = 20
TOP_IO_WAIT_USERS_LIMIT = 10


def mask_user(user, aliases):
    if user not in aliases:
        aliases[user] = f"user-{len(aliases) + 1:02d}"
    return aliases[user]


def aggregate(lines, total_cpu, mask_users=False, aliases=None):
    aliases = aliases or {}
    user_cpu = {}
    io_wait_users = {}
    total_cpu_percent = 0.0
    r_count = 0
    d_count = 0

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue

        user = mask_user(parts[0], aliases) if mask_users else parts[0]
        state = parts[2]

        try:
            raw_cpu_percent = float(parts[1])
        except ValueError:
            continue

        user_cpu[user] = user_cpu.get(user, 0.0) + raw_cpu_percent
        total_cpu_percent += raw_cpu_percent

        if state.startswith("R"):
            r_count += 1
        elif state.startswith("D"):
            d_count += 1
            io_wait_users[user] = io_wait_users.get(user, 0) + 1

    top_users = sorted(user_cpu.items(), key=lambda x: x[1], reverse=True)[:TOP_USERS_LIMIT]
    top_io_wait_users = sorted(io_wait_users.items(), key=lambda x: x[1], reverse=True)[:TOP_IO_WAIT_USERS_LIMIT]

    return {
        "top_users": [
            {
                "user": user,
                "raw_cpu_percent": round(raw_cpu_percent, 1),
                "cpu_util_percent": round(raw_cpu_percent / total_cpu if total_cpu > 0 else 0.0, 1),
            }
            for user, raw_cpu_percent in top_users
        ],
        "io_wait_users": [
            {"user": user, "d_count": count}
            for user, count in top_io_wait_users
        ],
        "cpu_util": round(total_cpu_percent / total_cpu if total_cpu > 0 else 0.0, 1),
        "r_count": r_count,
        "d_count": d_count,
    }


def fetch(host, mask_users=False, aliases=None):
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        host,
        "cat /proc/loadavg; nproc; ps -eo user,pcpu,state --no-headers",
    ]

    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=SSH_CMD_TIMEOUT,
        ).strip().splitlines()
    except subprocess.TimeoutExpired:
        return {"host": host, "ok": False, "error": "timeout"}
    except Exception as exc:
        return {"host": host, "ok": False, "error": str(exc)}

    if len(out) < 2:
        return {"host": host, "ok": False, "error": "invalid output"}

    try:
        load = out[0].split()
        cpu = int(out[1].strip())
        l1, l5, l15 = map(float, load[:3])
    except (ValueError, IndexError):
        return {"host": host, "ok": False, "error": "failed to parse command output"}

    agg = aggregate(out[2:], cpu, mask_users=mask_users, aliases=aliases)

    return {
        "host": host,
        "ok": True,
        "cpu": cpu,
        "l1": l1,
        "l5": l5,
        "l15": l15,
        "ratio": round(l1 / cpu, 2) if cpu > 0 else 0.0,
        "cpu_util": agg["cpu_util"],
        "r_count": agg["r_count"],
        "d_count": agg["d_count"],
        "top_users": agg["top_users"],
        "io_wait_users": agg["io_wait_users"],
    }


def load_hosts(args):
    hosts = list(args.hosts or [])

    if args.hosts_file:
        for line in Path(args.hosts_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                hosts.append(line)

    deduped = []
    for host in hosts:
        if host not in deduped:
            deduped.append(host)

    if not deduped:
        raise SystemExit("No hosts provided. Use host arguments or --hosts-file.")

    return deduped


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp = f.name

    Path(tmp).replace(path)


def parse_args():
    parser = argparse.ArgumentParser(description="Collect Linux server load snapshots over SSH.")
    parser.add_argument("hosts", nargs="*", help="Hosts to poll, e.g. compute-a01 compute-a02")
    parser.add_argument("--hosts-file", help="Newline-delimited host list")
    parser.add_argument("--mask-users", action="store_true", help="Replace usernames with user-01, user-02, ...")
    return parser.parse_args()


def main():
    args = parse_args()
    hosts = load_hosts(args)
    aliases = {}

    while True:
        started = time.time()
        payload = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": [fetch(host, mask_users=args.mask_users, aliases=aliases) for host in hosts],
        }
        write_atomic(DATA_FILE, payload)

        elapsed = time.time() - started
        time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()
