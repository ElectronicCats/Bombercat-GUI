"""Tarjeta EMV simulada para tests offline (sin hardware).

`build_fake_card()` devuelve `(send, state)` donde `send` es un `Transceiver`
(mapea APDU->Response) y `state` registra datos útiles para aserciones (p.ej. el
PDOL que recibió el GPO, para verificar la construcción de DOL desde el perfil).
"""

from __future__ import annotations

from emvy.core import apdu, tlv
from emvy.core.hexutil import from_hex, to_hex

AID = "A0000000041010"
FLAG = "flag{emv_ctf_pwn}"
TRACK2 = "4761739001010010D2512201" + "0" * 8


def _ppse_fci() -> bytes:
    return tlv.encode_tlv(
        tlv.TLV(
            "6F",
            b"",
            [
                tlv.tlv("84", b"2PAY.SYS.DDF01"),
                tlv.TLV(
                    "A5",
                    b"",
                    [
                        tlv.TLV(
                            "BF0C",
                            b"",
                            [
                                tlv.TLV(
                                    "61",
                                    b"",
                                    [
                                        tlv.tlv("4F", from_hex(AID)),
                                        tlv.tlv("50", b"MASTERCARD"),
                                        tlv.tlv("87", b"\x01"),
                                    ],
                                    constructed=True,
                                ),
                            ],
                            constructed=True,
                        )
                    ],
                    constructed=True,
                ),
            ],
            constructed=True,
        )
    )


def _aid_fci() -> bytes:
    # FCI con PDOL (9F38) que pide 9F37 (4) y 9F02 (6)
    a5 = tlv.TLV(
        "A5",
        b"",
        [
            tlv.tlv("50", b"MASTERCARD"),
            tlv.tlv("9F38", from_hex("9F3704" "9F0206")),
        ],
        constructed=True,
    )
    return tlv.encode_tlv(
        tlv.TLV(
            "6F",
            b"",
            [
                tlv.tlv("84", from_hex(AID)),
                a5,
            ],
            constructed=True,
        )
    )


def _record() -> bytes:
    return tlv.encode_tlv(
        tlv.TLV(
            "70",
            b"",
            [
                tlv.tlv("5A", from_hex("4761739001010010")),
                tlv.tlv("57", from_hex(TRACK2)),
                tlv.tlv("5F24", from_hex("251231")),
                tlv.tlv("5F20", b"EMVY/CTF TEST"),
                tlv.tlv("DFAE01", FLAG.encode()),
            ],
            constructed=True,
        )
    )


def build_fake_card():
    ppse, aidf, rec = _ppse_fci(), _aid_fci(), _record()
    gpo = tlv.encode_tlv(tlv.tlv("80", from_hex("1980") + from_hex("08010100")))
    atc = tlv.encode_tlv(tlv.tlv("9F36", from_hex("0005")))
    state: dict = {"gpo_pdol": None}

    def send(a) -> apdu.Response:
        b = a.to_bytes() if isinstance(a, apdu.APDU) else bytes(a)
        h = to_hex(b)
        if h.startswith("00A40400") and b"2PAY.SYS.DDF01" in b:
            return apdu.Response(ppse, 0x90, 0x00)
        if h.startswith("00A40400") and from_hex(AID) in b:
            return apdu.Response(aidf, 0x90, 0x00)
        if h.startswith("00A40400"):  # PSE u otros AIDs: no encontrado
            return apdu.Response(b"", 0x6A, 0x82)
        if h.startswith("80A80000"):  # GPO: registra el PDOL recibido (dentro de 83)
            payload = b[5 : 5 + b[4]]
            state["gpo_pdol"] = to_hex(payload[2:])  # quita tag/len de 83
            return apdu.Response(gpo, 0x90, 0x00)
        if h.startswith("00B2") and b[3] == ((1 << 3) | 4) and b[2] == 1:  # SFI1 REC1
            return apdu.Response(rec, 0x90, 0x00)
        if h.startswith("80CA9F36"):
            return apdu.Response(atc, 0x90, 0x00)
        return apdu.Response(b"", 0x6A, 0x82)

    return send, state
