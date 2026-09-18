"""Diccionario de tags EMV (BER-TLV). tag hex (mayúsculas) -> (nombre, formato).

`fmt` sugiere cómo interpretar/codificar el valor:
  b=binario/hex, n=numérico (BCD), an/ans=texto ASCII, cn=comprimido numérico.
"""

from __future__ import annotations

# tag -> (nombre, fmt)
TAGS: dict[str, tuple[str, str]] = {
    "4F": ("AID - Application Identifier (tarjeta)", "b"),
    "50": ("Application Label", "ans"),
    "57": ("Track 2 Equivalent Data", "b"),
    "5A": ("Application PAN", "cn"),
    "5F20": ("Cardholder Name", "ans"),
    "5F24": ("Application Expiration Date (YYMMDD)", "n"),
    "5F25": ("Application Effective Date (YYMMDD)", "n"),
    "5F28": ("Issuer Country Code", "n"),
    "5F2A": ("Transaction Currency Code", "n"),
    "5F2D": ("Language Preference", "an"),
    "5F30": ("Service Code", "n"),
    "5F34": ("Application PAN Sequence Number", "n"),
    "5F36": ("Transaction Currency Exponent", "n"),
    "5F50": ("Issuer URL", "ans"),
    "5F53": ("IBAN", "b"),
    "5F54": ("Bank Identifier Code (BIC)", "ans"),
    "5F55": ("Issuer Country Code (alpha2)", "an"),
    "5F56": ("Issuer Country Code (alpha3)", "an"),
    "61": ("Application Template (directorio)", "b"),
    "6F": ("FCI Template", "b"),
    "70": ("READ RECORD Response Template / AEF", "b"),
    "71": ("Issuer Script Template 1", "b"),
    "72": ("Issuer Script Template 2", "b"),
    "73": ("Directory Discretionary Template", "b"),
    "77": ("Response Message Template Format 2", "b"),
    "80": ("Response Message Template Format 1", "b"),
    "81": ("Amount, Authorised (binary)", "b"),
    "82": ("Application Interchange Profile (AIP)", "b"),
    "83": ("Command Template (GPO)", "b"),
    "84": ("Dedicated File (DF) Name", "b"),
    "86": ("Issuer Script Command", "b"),
    "87": ("Application Priority Indicator", "b"),
    "88": ("Short File Identifier (SFI)", "b"),
    "89": ("Authorisation Code", "b"),
    "8A": ("Authorisation Response Code (ARC)", "an"),
    "8C": ("CDOL1 - Card Risk Mgmt Data Object List 1", "b"),
    "8D": ("CDOL2 - Card Risk Mgmt Data Object List 2", "b"),
    "8E": ("CVM List", "b"),
    "8F": ("Certification Authority Public Key Index (CA PK Index)", "b"),
    "90": ("Issuer Public Key Certificate", "b"),
    "91": ("Issuer Authentication Data", "b"),
    "92": ("Issuer Public Key Remainder", "b"),
    "93": ("Signed Static Application Data (SSAD)", "b"),
    "94": ("Application File Locator (AFL)", "b"),
    "95": ("Terminal Verification Results (TVR)", "b"),
    "97": ("Transaction Certificate Data Object List (TDOL)", "b"),
    "98": ("Transaction Certificate (TC) Hash Value", "b"),
    "99": ("Transaction PIN Data", "b"),
    "9A": ("Transaction Date (YYMMDD)", "n"),
    "9B": ("Transaction Status Information (TSI)", "b"),
    "9C": ("Transaction Type", "n"),
    "9D": ("DDF Name", "b"),
    "9F01": ("Acquirer Identifier", "n"),
    "9F02": ("Amount, Authorised (Numeric)", "n"),
    "9F03": ("Amount, Other (Numeric)", "n"),
    "9F04": ("Amount, Other (Binary)", "b"),
    "9F05": ("Application Discretionary Data", "b"),
    "9F06": ("AID - Application Identifier (terminal)", "b"),
    "9F07": ("Application Usage Control (AUC)", "b"),
    "9F08": ("Application Version Number (ICC)", "b"),
    "9F09": ("Application Version Number (Terminal)", "b"),
    "9F0B": ("Cardholder Name Extended", "ans"),
    "9F0D": ("Issuer Action Code - Default (IAC Default)", "b"),
    "9F0E": ("Issuer Action Code - Denial (IAC Denial)", "b"),
    "9F0F": ("Issuer Action Code - Online (IAC Online)", "b"),
    "9F10": ("Issuer Application Data (IAD)", "b"),
    "9F11": ("Issuer Code Table Index", "n"),
    "9F12": ("Application Preferred Name", "ans"),
    "9F13": ("Last Online ATC Register", "b"),
    "9F14": ("Lower Consecutive Offline Limit", "b"),
    "9F15": ("Merchant Category Code (MCC)", "n"),
    "9F16": ("Merchant Identifier", "ans"),
    "9F17": ("PIN Try Counter", "b"),
    "9F18": ("Issuer Script Identifier", "b"),
    "9F1A": ("Terminal Country Code", "n"),
    "9F1B": ("Terminal Floor Limit", "b"),
    "9F1C": ("Terminal Identification", "an"),
    "9F1D": ("Terminal Risk Management Data", "b"),
    "9F1E": ("Interface Device (IFD) Serial Number", "an"),
    "9F1F": ("Track 1 Discretionary Data", "ans"),
    "9F20": ("Track 2 Discretionary Data", "cn"),
    "9F21": ("Transaction Time (HHMMSS)", "n"),
    "9F22": ("CA Public Key Index (Terminal)", "b"),
    "9F23": ("Upper Consecutive Offline Limit", "b"),
    "9F26": ("Application Cryptogram (ARQC/TC/AAC)", "b"),
    "9F27": ("Cryptogram Information Data (CID)", "b"),
    "9F2A": ("Kernel Identifier", "b"),
    "9F2D": ("ICC PIN Encipherment Public Key Certificate", "b"),
    "9F2E": ("ICC PIN Encipherment Public Key Exponent", "b"),
    "9F2F": ("ICC PIN Encipherment Public Key Remainder", "b"),
    "9F32": ("Issuer Public Key Exponent", "b"),
    "9F33": ("Terminal Capabilities", "b"),
    "9F34": ("CVM Results", "b"),
    "9F35": ("Terminal Type", "n"),
    "9F36": ("Application Transaction Counter (ATC)", "b"),
    "9F37": ("Unpredictable Number (UN)", "b"),
    "9F38": ("Processing Options Data Object List (PDOL)", "b"),
    "9F39": ("Point-of-Service (POS) Entry Mode", "n"),
    "9F3A": ("Amount, Reference Currency", "b"),
    "9F3B": ("Application Reference Currency", "n"),
    "9F3C": ("Transaction Reference Currency Code", "n"),
    "9F3D": ("Transaction Reference Currency Exponent", "n"),
    "9F40": ("Additional Terminal Capabilities", "b"),
    "9F41": ("Transaction Sequence Counter", "n"),
    "9F42": ("Application Currency Code", "n"),
    "9F43": ("Application Reference Currency Exponent", "n"),
    "9F44": ("Application Currency Exponent", "n"),
    "9F45": ("Data Authentication Code", "b"),
    "9F46": ("ICC Public Key Certificate", "b"),
    "9F47": ("ICC Public Key Exponent", "b"),
    "9F48": ("ICC Public Key Remainder", "b"),
    "9F49": ("Dynamic Data Authentication DOL (DDOL)", "b"),
    "9F4A": ("Static Data Authentication Tag List (SDA Tag List)", "b"),
    "9F4B": ("Signed Dynamic Application Data (SDAD)", "b"),
    "9F4C": ("ICC Dynamic Number", "b"),
    "9F4D": ("Log Entry (SFI + nº registros)", "b"),
    "9F4E": ("Merchant Name and Location", "ans"),
    "9F4F": ("Log Format (transaction log)", "b"),
    "9F50": ("Offline Accumulator Balance", "b"),
    "9F51": ("Application Currency Code (contactless)", "n"),
    "9F52": ("Application Default Action (ADA)", "b"),
    "9F53": ("Consecutive Transaction Counter Intl Limit", "b"),
    "9F54": ("Cumulative Total Tx Amount Limit", "b"),
    "9F55": ("Geographic Indicator", "b"),
    "9F56": ("Issuer Authentication Indicator", "b"),
    "9F57": ("Issuer Country Code", "n"),
    "9F58": ("Lower Consecutive Offline Limit (card)", "b"),
    "9F59": ("Upper Consecutive Offline Limit (card)", "b"),
    "9F5A": ("Application Program Identifier", "b"),
    "9F5B": ("Issuer Script Results", "b"),
    "9F66": ("Terminal Transaction Qualifiers (TTQ)", "b"),
    "9F6C": ("Card Transaction Qualifiers (CTQ)", "b"),
    "9F6E": ("Form Factor Indicator / Third Party Data", "b"),
    "9F7C": ("Customer Exclusive Data (CED)", "b"),
    "A5": ("FCI Proprietary Template", "b"),
    "BF0C": ("FCI Issuer Discretionary Data", "b"),
    "DF": ("Issuer/Proprietario (RFU)", "b"),
}


def tag_name(tag: str) -> str:
    """Nombre del tag, o etiqueta genérica si es desconocido/propietario."""
    tag = tag.upper()
    if tag in TAGS:
        return TAGS[tag][0]
    # Tags propietarios de emisor suelen empezar en 9Fxx / DFxx / BFxx
    if tag.startswith("DF"):
        return "Proprietary (emisor, DFxx)"
    if tag.startswith("9F") or tag.startswith("BF"):
        return "Proprietary / desconocido"
    return "Desconocido"


def tag_fmt(tag: str) -> str:
    """Formato sugerido del tag (b/n/an/ans/cn); 'b' si es desconocido."""
    return TAGS.get(tag.upper(), ("", "b"))[1]


def is_constructed(tag: str) -> bool:
    """True si el primer byte del tag tiene el bit 0x20 (template constructivo)."""
    return bool(int(tag[:2], 16) & 0x20)
