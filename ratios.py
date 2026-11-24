def divide(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def leverage_flag(value):
    if value is None:
        return "No data"
    if value < 3:
        return "Green"
    if value <= 5:
        return "Amber"
    return "Red"


def cover_flag(value):
    # higher is better here
    if value is None:
        return "No data"
    if value > 4:
        return "Green"
    if value >= 2:
        return "Amber"
    return "Red"


def ratios_for(v):
    # v = one year's figures
    net_debt = None
    if v.get("debt") is not None and v.get("cash") is not None:
        net_debt = v["debt"] - v["cash"]

    ebitda = v.get("ebitda")
    leverage = divide(net_debt, ebitda)
    cover = divide(ebitda, v.get("interest"))
    margin = divide(v.get("net_income"), v.get("revenue"))

    lev_flag = leverage_flag(leverage)
    # negative EBITDA gives negative leverage, which would show green
    if ebitda is not None and ebitda <= 0 and net_debt is not None and net_debt > 0:
        leverage = None
        lev_flag = "Red"

    def rounded(x, places):
        return None if x is None else round(x, places)

    return {
        "Net debt (m)": rounded(net_debt, 1),
        "Net debt / EBITDA": rounded(leverage, 2),
        "Interest cover": rounded(cover, 2),
        "Profit margin %": None if margin is None else round(margin * 100, 1),
        "Leverage flag": lev_flag,
        "Cover flag": cover_flag(cover),
    }


def compute(figures):
    this_year = {f["figure"]: f["current_m"] for f in figures}
    last_year = {f["figure"]: f["prior_m"] for f in figures}
    return {"current": ratios_for(this_year), "prior": ratios_for(last_year)}


def sanity_warnings(figures):
    # catches wrong column / unit / line
    v = {f["figure"]: f["current_m"] for f in figures}
    warnings = []

    if v.get("ebitda") and v.get("revenue") and v["ebitda"] > v["revenue"]:
        warnings.append("EBITDA is bigger than revenue, which is almost impossible. Check both figures.")
    if v.get("net_income") and v.get("revenue") and v["net_income"] > v["revenue"]:
        warnings.append("Profit is bigger than revenue. Check both figures.")

    # e.g. 0.1 vs 1,250 - wrong unit
    biggest = max(abs(v.get("revenue") or 0), abs(v.get("ebitda") or 0))
    if v.get("net_income") and biggest and abs(v["net_income"]) < biggest * 0.001:
        warnings.append("Net income is tiny next to revenue/EBITDA. The unit is probably wrong "
                        "(thousands vs millions). Check it.")

    # roughly the interest rate. under 2% usually means it took one line from a note
    if v.get("interest") and v.get("debt"):
        rate = v["interest"] / v["debt"]
        if rate < 0.02:
            warnings.append(f"Interest is only {rate:.1%} of debt, which is too low to be the full bill. "
                            "It may be one line from a note rather than total finance costs.")
        elif rate > 0.25:
            warnings.append(f"Interest is {rate:.0%} of debt, which is unusually high. Check both figures.")

    currencies = {f["currency"] for f in figures if f["currency"] and f["current_m"] is not None}
    if len(currencies) > 1:
        warnings.append(f"Figures use different currencies ({', '.join(sorted(currencies))}).")

    units = {f["unit"] for f in figures if f["unit"] and f["current_m"] is not None}
    if len(units) > 1:
        warnings.append(f"Figures use different units ({', '.join(sorted(units))}). Check the conversion.")

    # 5x jump usually = unit mix up
    for f in figures:
        # skip profit -> loss
        if f["current_m"] and f["prior_m"] and (f["current_m"] > 0) == (f["prior_m"] > 0):
            change = f["current_m"] / f["prior_m"]
            if change > 5 or change < 0.2:
                warnings.append(f"{f['figure']} changed more than 5x between years. "
                                "Possible unit or column mix-up.")

    years = {f["year"] for f in figures if f["year"] and f["current_m"] is not None}
    if len(years) > 1:
        warnings.append(f"Figures come from different years ({', '.join(sorted(map(str, years)))}).")

    return warnings
