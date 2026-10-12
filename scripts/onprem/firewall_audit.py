#!/usr/bin/env python3
"""Windows 방화벽 로그(pfirewall.log)에서 '사내망 밖으로 나가려던 접속'만 골라 보여주는 점검 도구.

온프리미스(내부망) 운영 점검용 — 코드를 모두 고쳐도 라이브러리가 몰래 외부로 접속하는 일이 없는지
방화벽 로그로 확인한다. 표준 라이브러리만 사용하므로 파이썬만 있으면 어느 PC에서나 실행된다.

사용 예 (PowerShell):
    python firewall_audit.py C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log ^
        --allow-mail 142.250.0.0/15:587

분류 기준 (SEND, 즉 이 PC에서 밖으로 나가는 방향만 본다):
    내부        목적지가 사설/루프백/링크로컬/멀티캐스트/브로드캐스트 대역 (+ --internal 로 추가한 대역)
    허용(메일)  --allow-mail 로 지정한 메일 서버(대역/포트). 메일 발송은 점검 제외 대상(사용자 지시)
    확인 필요   그 밖의 모든 외부 접속 (ALLOW=실제로 나감, DROP=차단되었지만 시도가 있었음)

종료코드: 0 = 확인 필요 없음 / 1 = 확인 필요 있음 / 2 = 입력 파일 없음 또는 형식 오류
"""
from __future__ import annotations

import argparse
import ipaddress
import sys
from collections import defaultdict
from dataclasses import dataclass, field

DEFAULT_FIELDS = (
    "date time action protocol src-ip dst-ip src-port dst-port size tcpflags tcpsyn tcpack tcpwin "
    "icmptype icmpcode info path"
).split()

EXIT_OK, EXIT_REVIEW, EXIT_ERROR = 0, 1, 2


@dataclass(frozen=True)
class MailRule:
    network: ipaddress._BaseNetwork
    port: int | None  # None = 모든 포트

    def matches(self, ip: ipaddress._BaseAddress, port: int | None) -> bool:
        if ip.version != self.network.version or ip not in self.network:
            return False
        return self.port is None or self.port == port


@dataclass
class Finding:
    key: tuple[str, str, str, str]  # (action, protocol, dst-ip, dst-port)
    count: int = 0
    first: str = ""
    last: str = ""
    sources: set[str] = field(default_factory=set)


@dataclass
class Report:
    internal: int = 0
    mail: int = 0
    review: dict[tuple[str, str, str, str], Finding] = field(default_factory=dict)
    skipped_lines: int = 0
    parsed_lines: int = 0
    inbound_ignored: int = 0


def parse_mail_rule(text: str) -> MailRule:
    """'ip', 'cidr', 'ip:port', 'cidr:port' (IPv6 는 포트 없이 'addr' 또는 'addr/prefix')."""
    text = text.strip()
    port: int | None = None
    if text.count(":") == 1:  # IPv4 + 포트
        text, port_text = text.split(":")
        port = int(port_text)
        if not 0 < port < 65536:
            raise ValueError(f"포트 범위 오류: {port}")
    network = ipaddress.ip_network(text, strict=False)
    return MailRule(network, port)


def is_internal(ip: ipaddress._BaseAddress, extra: list[ipaddress._BaseNetwork]) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip == ipaddress.IPv4Address("255.255.255.255"):
        return True
    return any(ip.version == net.version and ip in net for net in extra)


def analyze(lines, mail_rules: list[MailRule], internal_nets: list[ipaddress._BaseNetwork]) -> Report:
    report = Report()
    fields = list(DEFAULT_FIELDS)
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.lower().startswith("#fields:"):
                fields = line.split(":", 1)[1].split()
            continue
        parts = line.split()
        try:
            row = dict(zip(fields, parts))
            if len(parts) < len(fields):
                raise ValueError("열 수 부족")
            path = row["path"].upper()
            action = row["action"].upper()
            protocol = row["protocol"].upper()
            dst_ip = ipaddress.ip_address(row["dst-ip"])
            dst_port_text = row["dst-port"]
            dst_port = int(dst_port_text) if dst_port_text.isdigit() else None
            stamp = f'{row["date"]} {row["time"]}'
            src = row["src-ip"]
        except (KeyError, ValueError):
            report.skipped_lines += 1
            continue
        report.parsed_lines += 1
        if path != "SEND":  # 수신(RECEIVE)·기타 방향은 '밖으로 나감' 점검 대상이 아니다
            report.inbound_ignored += 1
            continue
        if is_internal(dst_ip, internal_nets):
            report.internal += 1
            continue
        if any(rule.matches(dst_ip, dst_port) for rule in mail_rules):
            report.mail += 1
            continue
        key = (action, protocol, str(dst_ip), dst_port_text)
        finding = report.review.setdefault(key, Finding(key=key, first=stamp))
        finding.count += 1
        finding.last = stamp
        finding.sources.add(src)
    return report


def render(report: Report) -> str:
    out = [
        "=== 방화벽 아웃바운드 점검 결과 ===",
        f"읽은 로그 줄: {report.parsed_lines}건 (형식 오류로 건너뜀 {report.skipped_lines}건, 수신 방향 제외 {report.inbound_ignored}건)",
        f"  내부 통신:            {report.internal}건",
        f"  허용(메일, 점검 제외): {report.mail}건",
        f"  확인 필요(외부 접속):  {sum(f.count for f in report.review.values())}건 / 목적지 {len(report.review)}곳",
    ]
    if report.review:
        out.append("")
        out.append("[확인 필요] ALLOW=실제로 밖으로 나감, DROP=차단됐지만 시도가 있었음")
        out.append(f"{'결과':<6}{'프로토콜':<8}{'목적지':<40}{'횟수':>6}  최초 ~ 최종 / 출발 PC")
        for f in sorted(report.review.values(), key=lambda x: (-x.count, x.key)):
            action, proto, ip, port = f.key
            dest = f"{ip}:{port}"
            out.append(
                f"{action:<6}{proto:<8}{dest:<40}{f.count:>6}  {f.first} ~ {f.last} / {', '.join(sorted(f.sources))}"
            )
        out.append("")
        out.append("다음 할 일: 위 목적지를 사용하는 프로그램을 찾아(예: 해당 시각의 워커/백엔드 로그) 원인을 확인한다.")
    else:
        out.append("")
        out.append("결과: 메일 서버를 제외한 외부 접속 시도가 없습니다.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="방화벽 로그에서 사내망 밖으로 나가려던 접속을 찾는다.")
    parser.add_argument("logfile", help="pfirewall.log 경로")
    parser.add_argument("--allow-mail", action="append", default=[], metavar="IP[/PREFIX][:PORT]",
                        help="점검에서 제외할 메일 서버(여러 번 지정 가능). 예: 142.250.0.0/15:587")
    parser.add_argument("--internal", action="append", default=[], metavar="CIDR",
                        help="사설 대역이 아니지만 사내망으로 취급할 대역(여러 번 지정 가능)")
    args = parser.parse_args(argv)

    try:
        mail_rules = [parse_mail_rule(t) for t in args.allow_mail]
        internal_nets = [ipaddress.ip_network(t, strict=False) for t in args.internal]
    except ValueError as exc:
        print(f"[오류] 허용/내부 대역 형식이 올바르지 않습니다: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        with open(args.logfile, encoding="utf-8", errors="replace") as fh:
            report = analyze(fh, mail_rules, internal_nets)
    except OSError as exc:
        print(f"[오류] 로그 파일을 읽을 수 없습니다: {exc}\n"
              "방화벽 로그가 켜져 있는지, 관리자 권한으로 실행했는지 확인하세요.", file=sys.stderr)
        return EXIT_ERROR

    if report.parsed_lines == 0 and report.skipped_lines > 0:
        print("[오류] 읽을 수 있는 로그 줄이 없습니다. pfirewall.log 형식이 맞는지 확인하세요.", file=sys.stderr)
        return EXIT_ERROR
    if report.parsed_lines == 0:
        print("[오류] 로그에 기록된 접속이 없습니다. 방화벽 로그(허용/차단)가 켜져 있고 면접을 진행한 뒤인지 확인하세요.",
              file=sys.stderr)
        return EXIT_ERROR

    print(render(report))
    return EXIT_REVIEW if report.review else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
