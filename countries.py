#utf-8

COUNTRIES = [
    ("Afghanistan", "AF", "93"), ("Albania", "AL", "355"), ("Algeria", "DZ", "213"),
    ("Argentina", "AR", "54"), ("Australia", "AU", "61"), ("Austria", "AT", "43"),
    ("Bangladesh", "BD", "880"), ("Belgium", "BE", "32"), ("Bolivia", "BO", "591"),
    ("Brazil", "BR", "55"), ("Bulgaria", "BG", "359"), ("Cambodia", "KH", "855"),
    ("Cameroon", "CM", "237"), ("Canada", "CA", "1"), ("Chile", "CL", "56"),
    ("China", "CN", "86"), ("Colombia", "CO", "57"), ("Costa Rica", "CR", "506"),
    ("Croatia", "HR", "385"), ("Cuba", "CU", "53"), ("Czechia", "CZ", "420"),
    ("Denmark", "DK", "45"), ("Dominican Republic", "DO", "1"), ("Ecuador", "EC", "593"),
    ("Egypt", "EG", "20"), ("El Salvador", "SV", "503"), ("Estonia", "EE", "372"),
    ("Ethiopia", "ET", "251"), ("Finland", "FI", "358"), ("France", "FR", "33"),
    ("Germany", "DE", "49"), ("Ghana", "GH", "233"), ("Greece", "GR", "30"),
    ("Guatemala", "GT", "502"), ("Honduras", "HN", "504"), ("Hong Kong", "HK", "852"),
    ("Hungary", "HU", "36"), ("Iceland", "IS", "354"), ("India", "IN", "91"),
    ("Indonesia", "ID", "62"), ("Iran", "IR", "98"), ("Iraq", "IQ", "964"),
    ("Ireland", "IE", "353"), ("Israel", "IL", "972"), ("Italy", "IT", "39"),
    ("Ivory Coast", "CI", "225"), ("Japan", "JP", "81"), ("Jordan", "JO", "962"),
    ("Kazakhstan", "KZ", "7"), ("Kenya", "KE", "254"), ("Kuwait", "KW", "965"),
    ("Latvia", "LV", "371"), ("Lebanon", "LB", "961"), ("Lithuania", "LT", "370"),
    ("Luxembourg", "LU", "352"), ("Madagascar", "MG", "261"), ("Malaysia", "MY", "60"),
    ("Mali", "ML", "223"), ("Malta", "MT", "356"), ("Mexico", "MX", "52"),
    ("Morocco", "MA", "212"), ("Netherlands", "NL", "31"), ("New Zealand", "NZ", "64"),
    ("Nigeria", "NG", "234"), ("Norway", "NO", "47"), ("Pakistan", "PK", "92"),
    ("Panama", "PA", "507"), ("Paraguay", "PY", "595"), ("Peru", "PE", "51"),
    ("Philippines", "PH", "63"), ("Poland", "PL", "48"), ("Portugal", "PT", "351"),
    ("Qatar", "QA", "974"), ("Romania", "RO", "40"), ("Russia", "RU", "7"),
    ("Saudi Arabia", "SA", "966"), ("Senegal", "SN", "221"), ("Serbia", "RS", "381"),
    ("Singapore", "SG", "65"), ("Slovakia", "SK", "421"), ("Slovenia", "SI", "386"),
    ("South Africa", "ZA", "27"), ("South Korea", "KR", "82"), ("Spain", "ES", "34"),
    ("Sri Lanka", "LK", "94"), ("Sweden", "SE", "46"), ("Switzerland", "CH", "41"),
    ("Taiwan", "TW", "886"), ("Tanzania", "TZ", "255"), ("Thailand", "TH", "66"),
    ("Tunisia", "TN", "216"), ("Turkey", "TR", "90"), ("Ukraine", "UA", "380"),
    ("United Arab Emirates", "AE", "971"), ("United Kingdom", "GB", "44"),
    ("United States", "US", "1"), ("Uruguay", "UY", "598"), ("Venezuela", "VE", "58"),
    ("Vietnam", "VN", "84"),
]


def flag(iso: str) -> str:
    iso = iso.upper()
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso if "A" <= c <= "Z")


def populate_country_combo(combo, default_iso="FR"):
    from PyQt6.QtWidgets import QComboBox, QCompleter
    from PyQt6.QtCore import Qt

    default_idx = 0
    for i, (name, iso, dial) in enumerate(sorted(COUNTRIES, key=lambda c: c[0])):
        combo.addItem(f"{flag(iso)}  {name}  +{dial}", f"+{dial}")
        if iso == default_iso:
            default_idx = i

    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    le = combo.lineEdit()
    if le is not None:
        le.setReadOnly(False)
    comp = combo.completer()
    if comp is not None:
        comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    combo.setCurrentIndex(default_idx)
    return combo
