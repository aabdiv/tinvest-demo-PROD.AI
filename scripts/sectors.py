"""Ручная разметка отраслей для крупных тикеров Мосбиржи.

Она важнее разметки LLM: от отрасли зависят красные линии («без нефти и газа»).
Тикеры, которых нет в этом словаре, размечает LLM при сборке базы.
Если тикер не торгуется, он просто не попадёт в базу.
"""

SECTOR_OVERRIDES = {
    # Банки и финансы
    "SBER": "banks_finance", "SBERP": "banks_finance", "VTBR": "banks_finance", "T": "banks_finance",
    "MOEX": "banks_finance", "CBOM": "banks_finance", "BSPB": "banks_finance", "SVCB": "banks_finance",
    "RENI": "banks_finance", "LEAS": "banks_finance", "SPBE": "banks_finance", "MBNK": "banks_finance",
    # Нефть и газ
    "GAZP": "oil_gas", "LKOH": "oil_gas", "ROSN": "oil_gas", "NVTK": "oil_gas", "TATN": "oil_gas",
    "TATNP": "oil_gas", "SNGS": "oil_gas", "SNGSP": "oil_gas", "TRNFP": "oil_gas", "BANE": "oil_gas",
    "BANEP": "oil_gas", "RNFT": "oil_gas",
    # Металлы и добыча
    "GMKN": "metals_mining", "PLZL": "metals_mining", "ALRS": "metals_mining", "CHMF": "metals_mining",
    "NLMK": "metals_mining", "MAGN": "metals_mining", "RUAL": "metals_mining", "MTLR": "metals_mining",
    "MTLRP": "metals_mining", "SELG": "metals_mining", "RASP": "metals_mining", "UGLD": "metals_mining",
    "ENPG": "metals_mining", "VSMO": "metals_mining", "TRMK": "metals_mining",
    # IT и интернет
    "YDEX": "it_internet", "OZON": "it_internet", "VKCO": "it_internet", "POSI": "it_internet",
    "HEAD": "it_internet", "ASTR": "it_internet", "CIAN": "it_internet", "WUSH": "it_internet",
    "DIAS": "it_internet", "IVAT": "it_internet", "SOFL": "it_internet", "DATA": "it_internet",
    # Телеком
    "MTSS": "telecom", "RTKM": "telecom", "RTKMP": "telecom",
    # Ретейл и потребительский сектор
    "MGNT": "consumer_retail", "X5": "consumer_retail", "LENT": "consumer_retail", "FIXR": "consumer_retail",
    "MVID": "consumer_retail", "BELU": "consumer_retail", "AQUA": "consumer_retail", "GCHE": "consumer_retail",
    "RAGR": "consumer_retail", "ABRD": "consumer_retail",
    # Электроэнергетика
    "IRAO": "utilities", "HYDR": "utilities", "FEES": "utilities", "UPRO": "utilities", "MSNG": "utilities",
    "OGKB": "utilities", "TGKA": "utilities", "MSRS": "utilities", "LSNG": "utilities", "LSNGP": "utilities",
    "MRKC": "utilities", "MRKP": "utilities",
    # Химия и удобрения
    "PHOR": "chemicals", "AKRN": "chemicals", "NKNC": "chemicals", "NKNCP": "chemicals", "KAZT": "chemicals",
    # Девелопмент
    "PIKK": "real_estate", "SMLT": "real_estate", "LSRG": "real_estate", "ETLN": "real_estate",
    # Транспорт и логистика
    "AFLT": "transport", "FLOT": "transport", "NMTP": "transport", "FESH": "transport", "DELI": "transport",
    # Промышленность
    "KMAZ": "industrial", "UWGN": "industrial", "IRKT": "industrial", "SVAV": "industrial",
    # Медицина и фарма
    "MDMG": "healthcare", "GEMC": "healthcare", "OZPH": "healthcare", "APTK": "healthcare",
    # Прочее
    "AFKS": "other", "SGZH": "other",
}
