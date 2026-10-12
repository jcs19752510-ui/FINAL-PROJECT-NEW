"""firewall_audit.py 내부 테스트 — 공개된 pfirewall.log 형식에 맞춘 합성 로그로 검증한다.
(실제 Windows PC의 로그로는 검증하지 못했다. 형식이 다르면 첫 실행에서 '형식 오류' 종료코드 2로 드러난다.)
실행: python -m pytest scripts/onprem/tests -q"""

import importlib.util
import pathlib
import sys

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "firewall_audit", pathlib.Path(__file__).resolve().parents[1] / "firewall_audit.py"
)
fa = importlib.util.module_from_spec(_SPEC)
sys.modules["firewall_audit"] = fa  # dataclass 가 모듈을 찾을 수 있도록 등록
_SPEC.loader.exec_module(fa)

HEADER = (
    "#Version: 1.5\n#Software: Microsoft Windows Firewall\n#Time Format: Local\n"
    "#Fields: date time action protocol src-ip dst-ip src-port dst-port size tcpflags tcpsyn tcpack tcpwin "
    "icmptype icmpcode info path\n"
)


def row(
    action="ALLOW",
    proto="TCP",
    src="192.168.0.5",
    dst="10.0.0.9",
    sport="51000",
    dport="8001",
    path="SEND",
    stamp="2026-10-12 10:00:00",
):
    return f"{stamp} {action} {proto} {src} {dst} {sport} {dport} 0 - 0 0 0 - - - {path}\n"


def run(tmp_path, body, *extra, header=HEADER):
    log = tmp_path / "pfirewall.log"
    log.write_text(header + body, encoding="utf-8")
    return fa.main([str(log), *extra])


def test_fw01_internal_only_exit0(tmp_path, capsys):
    body = row(dst="10.1.2.3") + row(dst="172.16.5.5") + row(dst="192.168.0.20") + row(dst="127.0.0.1")
    assert run(tmp_path, body) == 0
    assert "외부 접속 시도가 없습니다" in capsys.readouterr().out


def test_fw02_external_connection_exit1_and_listed(tmp_path, capsys):
    body = row(dst="8.8.8.8", dport="443") + row(dst="8.8.8.8", dport="443") + row(dst="10.0.0.1")
    assert run(tmp_path, body) == 1
    out = capsys.readouterr().out
    assert "8.8.8.8:443" in out and "확인 필요(외부 접속):  2건 / 목적지 1곳" in out


def test_fw03_mail_server_only_is_allowed_exit0(tmp_path, capsys):
    body = row(dst="142.250.1.1", dport="587")
    assert run(tmp_path, body, "--allow-mail", "142.250.0.0/15:587") == 0
    out = capsys.readouterr().out
    assert "허용(메일, 점검 제외): 1건" in out


def test_fw04_mail_ip_other_port_is_flagged(tmp_path):
    body = row(dst="142.250.1.1", dport="443")
    assert run(tmp_path, body, "--allow-mail", "142.250.0.0/15:587") == 1


def test_fw05_mail_rule_without_port_allows_any_port(tmp_path):
    assert run(tmp_path, row(dst="142.250.1.1", dport="465"), "--allow-mail", "142.250.1.1") == 0


def test_fw06_receive_direction_ignored(tmp_path, capsys):
    body = row(dst="203.0.113.9", path="RECEIVE") + row(dst="10.0.0.2")
    assert run(tmp_path, body) == 0
    assert "수신 방향 제외 1건" in capsys.readouterr().out


def test_fw07_dropped_attempt_still_reported(tmp_path, capsys):
    body = row(action="DROP", dst="1.1.1.1", dport="443")
    assert run(tmp_path, body) == 1
    assert "DROP" in capsys.readouterr().out


def test_fw08_ipv6_local_is_internal_global_is_not(tmp_path):
    assert run(tmp_path, row(dst="::1") + row(dst="fe80::1") + row(dst="fd00::5")) == 0
    assert run(tmp_path, row(dst="2606:4700:4700::1111", dport="443")) == 1


def test_fw09_multicast_and_broadcast_internal(tmp_path):
    body = row(dst="224.0.0.251", dport="5353", proto="UDP") + row(dst="255.255.255.255", dport="67", proto="UDP")
    assert run(tmp_path, body) == 0


def test_fw10_extra_internal_range(tmp_path):
    body = row(dst="100.64.1.5")  # CGNAT 대역: 사설이 아니므로 기본은 외부로 분류
    assert run(tmp_path, body) == 1
    assert run(tmp_path, body, "--internal", "100.64.0.0/10") == 0


def test_fw11_icmp_without_port(tmp_path, capsys):
    body = "2026-10-12 10:00:00 ALLOW ICMP 192.168.0.5 8.8.8.8 - - 60 - - - - 8 0 - SEND\n"
    assert run(tmp_path, body) == 1
    assert "8.8.8.8:-" in capsys.readouterr().out


def test_fw12_header_and_blank_lines_ignored(tmp_path):
    assert run(tmp_path, "\n" + row(dst="10.0.0.3") + "\n\n") == 0


def test_fw13_malformed_lines_skipped_with_count(tmp_path, capsys):
    body = "이건 깨진 줄\n" + row(dst="10.0.0.3") + "2026-10-12 25:00:00 ALLOW TCP\n"
    assert run(tmp_path, body) == 0
    assert "형식 오류로 건너뜀 2건" in capsys.readouterr().out


def test_fw14_all_malformed_exit2(tmp_path, capsys):
    assert run(tmp_path, "깨짐1\n깨짐2\n") == 2
    assert "형식" in capsys.readouterr().err


def test_fw15_empty_log_exit2(tmp_path, capsys):
    assert run(tmp_path, "") == 2
    assert "접속이 없습니다" in capsys.readouterr().err


def test_fw16_missing_file_exit2(tmp_path, capsys):
    assert fa.main([str(tmp_path / "없음.log")]) == 2
    assert "읽을 수 없습니다" in capsys.readouterr().err


def test_fw17_bad_allow_mail_argument_exit2(tmp_path, capsys):
    assert run(tmp_path, row(), "--allow-mail", "not-an-ip") == 2
    assert "형식이 올바르지" in capsys.readouterr().err


def test_fw18_missing_fields_header_uses_default_columns(tmp_path):
    body = row(dst="9.9.9.9", dport="53", proto="UDP")
    assert run(tmp_path, body, header="") == 1


def test_fw19_sorted_by_count_desc(tmp_path, capsys):
    body = row(dst="8.8.4.4", dport="53") + row(dst="1.1.1.1", dport="443") * 3
    run(tmp_path, body)
    out = capsys.readouterr().out
    assert out.index("1.1.1.1:443") < out.index("8.8.4.4:53")


def test_fw20_korean_path_and_utf8_log(tmp_path):
    log = tmp_path / "방화벽 로그.log"
    log.write_text(HEADER + row(dst="10.0.0.3"), encoding="utf-8")
    assert fa.main([str(log)]) == 0


@pytest.mark.parametrize("rule", ["142.250.0.0/15:587", "142.250.1.1", "142.250.1.1:25", "2001:db8::/32"])
def test_fw21_mail_rule_parsing_ok(rule):
    assert fa.parse_mail_rule(rule) is not None


@pytest.mark.parametrize("rule", ["abc", "1.2.3.4:99999", "1.2.3.4:x"])
def test_fw22_mail_rule_parsing_errors(rule):
    with pytest.raises(ValueError):
        fa.parse_mail_rule(rule)
