from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import time
import sys

import pexpect

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 2222
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "anything"
# Cowrie prompt pattern: user@hostname:/path# (or $ for non-root)
COWRIE_PROMPT = r"root@svr04:[^\$]*[$#] "


def load_sessions(path: str = SESSIONS_DIR) -> list[dict]:
    sessions = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            sessions.append(json.load(fh))
    return sessions


class CowrieDriver:
    """SSH driver that replays commands against a live Cowrie instance."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        user: str = DEFAULT_USER,
        password: str = DEFAULT_PASSWORD,
        timeout: int = 60,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self._child: pexpect.spawn | None = None

    def connect(self) -> None:
        self._child = pexpect.spawn(
            f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-p {self.port} {self.user}@{self.host}",
            timeout=self.timeout,
            encoding="utf-8",
            codec_errors="replace",
        )
        self._child.expect("password:")
        self._child.sendline(self.password)
        # Wait for the first shell prompt to confirm we're logged in
        self._child.expect(COWRIE_PROMPT, timeout=self.timeout)

    def disconnect(self) -> None:
        if self._child and self._child.isalive():
            try:
                self._child.sendline("exit")
                self._child.expect(pexpect.EOF, timeout=5)
            except Exception:
                pass
            self._child.close()

    def exec_command(self, command: str) -> tuple[str, float]:
        """Send a command and return (output, elapsed_seconds)."""
        if not self._child or not self._child.isalive():
            raise RuntimeError("SSH session not connected")

        start = time.perf_counter()
        self._child.sendline(command)

        matched = self._child.expect([COWRIE_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=self.timeout)
        elapsed = time.perf_counter() - start

        if matched == 1:
            return ("", elapsed)
        if matched == 2:
            return ("", elapsed)

        raw = self._child.before or ""
        lines = raw.strip().split("\n")
        if lines and lines[0].strip() == command:
            lines = lines[1:]
        output = "\n".join(lines).strip()
        return (output, elapsed)

    def __enter__(self) -> "CowrieDriver":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()


def normalize_output(text: str) -> str:
    """Normalize output for comparison: strip, collapse whitespace."""
    return " ".join(text.strip().split())


def check_step(step: dict, actual_output: str) -> tuple[bool, str | None]:
    """Check if actual_output matches step expectations. Returns (passed, reason)."""
    norm_actual = normalize_output(actual_output)

    if "expect" in step:
        norm_expected = normalize_output(step["expect"])
        if "expect_contains" in step:
            if norm_actual != norm_expected:
                return (False, f'exact expected "{norm_expected}", got "{norm_actual}"')
            for substr in step["expect_contains"]:
                if substr not in actual_output:
                    return (False, f'expected to contain "{substr}", got "{norm_actual}"')
            return (True, None)
        else:
            if norm_actual != norm_expected:
                return (False, f'exact expected "{norm_expected}", got "{norm_actual}"')
            return (True, None)

    if "expect_contains" in step:
        for substr in step["expect_contains"]:
            if substr not in actual_output:
                return (False, f'expected to contain "{substr}", got "{norm_actual}"')
        return (True, None)

    return (True, None)


DETECTION_PATTERNS = [
    "permission denied",
    "no such file or directory",
    "command not found",
    "does not exist",
    "internal error",
]


def check_detection_signals(output: str) -> list[str]:
    lowered = output.lower()
    return [p for p in DETECTION_PATTERNS if p in lowered]


def compute_metrics(steps_results: list[dict]) -> dict:
    total = len(steps_results)
    if total == 0:
        return {
            "state_consistency_rate": 1.0,
            "detection_signals_count": 0,
            "latency_p50": 0.0,
            "latency_p95": 0.0,
            "llm_call_rate": 1.0,
            "step_results": [],
        }

    passed = sum(1 for s in steps_results if s["passed"])
    state_consistency_rate = passed / total

    detection_count = sum(s["detection_signals_count"] for s in steps_results)

    latencies = [s["elapsed"] for s in steps_results]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.5)] if latencies_sorted else 0
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0

    return {
        "state_consistency_rate": round(state_consistency_rate, 4),
        "detection_signals_count": detection_count,
        "latency_p50": round(p50, 4),
        "latency_p95": round(p95, 4),
        "llm_call_rate": 1.0,
        "step_results": steps_results,
    }


def run_single_session(
    driver: CowrieDriver, session: dict, backend: str
) -> tuple[dict, dict]:
    """Run a single session and return (metrics, per_step_results)."""
    steps_results = []
    all_start = time.perf_counter()

    for i, step in enumerate(session["steps"]):
        command = step["cmd"]
        output, elapsed = driver.exec_command(command)

        passed, fail_reason = check_step(step, output)
        detection_signals = check_detection_signals(output)

        step_result = {
            "index": i,
            "command": command,
            "expected": step.get("expect"),
            "expected_contains": step.get("expect_contains"),
            "checks_state": step.get("checks_state"),
            "actual_output": output,
            "elapsed": round(elapsed, 4),
            "passed": passed,
            "fail_reason": fail_reason,
            "detection_signals": detection_signals,
            "detection_signals_count": len(detection_signals),
        }
        steps_results.append(step_result)

    total_elapsed = round(time.perf_counter() - all_start, 4)
    metrics = compute_metrics(steps_results)
    metrics["total_elapsed"] = total_elapsed
    return metrics, steps_results


def run(backend: str, sessions: list[dict], host: str, port: int) -> dict:
    """Replay sessions against a live Cowrie backend and compute metrics."""
    results = {
        "backend": backend,
        "host": host,
        "port": port,
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_sessions": len(sessions),
        "sessions": [],
        "aggregate": {},
    }

    all_metrics = []

    for session in sessions:
        sid = session.get("id", "unknown")
        print(f"  Running session: {sid} ({session.get('description', '')})")

        with CowrieDriver(host=host, port=port) as driver:
            metrics, steps_results = run_single_session(driver, session, backend)

        session_result = {
            "id": sid,
            "description": session.get("description"),
            "metrics": metrics,
        }
        results["sessions"].append(session_result)
        all_metrics.append(metrics)

        passed = metrics["state_consistency_rate"]
        print(f"    Consistency: {passed:.1%}  "
              f"Detections: {metrics['detection_signals_count']}  "
              f"p50: {metrics['latency_p50']:.2f}s  p95: {metrics['latency_p95']:.2f}s")

    if all_metrics:
        agg = {
            "state_consistency_rate": round(
                statistics.mean(m["state_consistency_rate"] for m in all_metrics), 4
            ),
            "detection_signals_count": sum(m["detection_signals_count"] for m in all_metrics),
            "latency_p50": round(
                statistics.mean(m["latency_p50"] for m in all_metrics), 4
            ),
            "latency_p95": round(
                statistics.mean(m["latency_p95"] for m in all_metrics), 4
            ),
            "llm_call_rate": 1.0,
            "total_elapsed": round(
                sum(m.get("total_elapsed", 0) for m in all_metrics), 4
            ),
            "total_commands": sum(len(m["step_results"]) for m in all_metrics),
            "total_passed": sum(
                sum(1 for sr in m["step_results"] if sr["passed"])
                for m in all_metrics
            ),
        }
        results["aggregate"] = agg

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="State-grounded honeypot evaluation harness"
    )
    parser.add_argument("--backend", choices=["vanilla", "grounded"], required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    sessions = load_sessions()
    if not sessions:
        print("No session files found in", SESSIONS_DIR)
        sys.exit(1)

    print(f"Loaded {len(sessions)} scripted session(s) from {SESSIONS_DIR}")
    for s in sessions:
        print(f"  - {s['id']}: {s['description']}")

    print(f"\nConnecting to Cowrie at {args.host}:{args.port}...")
    print(f"Running {len(sessions)} session(s) with backend '{args.backend}'...\n")

    results = run(args.backend, sessions, args.host, args.port)

    out_path = args.out or os.path.join(
        os.path.dirname(__file__), "results", f"{args.backend}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 64}")
    print(f"Results saved to {out_path}")
    agg = results["aggregate"]
    if agg:
        print(f"  Consistency rate:    {agg['state_consistency_rate']:.1%}")
        print(f"  Detection signals:   {agg['detection_signals_count']}")
        print(f"  Latency p50 / p95:   {agg['latency_p50']:.2f}s / {agg['latency_p95']:.2f}s")
        print(f"  Total commands:      {agg['total_commands']}")
        print(f"  Passed:              {agg['total_passed']}/{agg['total_commands']}")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()