import re

def parse_money(value):
    try:
        return float(value.replace(",", ""))
    except:
        match = re.search(r"\d+[.]?\d*", value)
        return float(match.group()) if match else 0.0


def token_usage_stub():
    return {
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0
    }
