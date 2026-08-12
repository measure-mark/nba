import re
def bs_filename_to_date(x:str) -> str:
    m = re.match(r'boxscores_(\d{8})0', x)
    if m is None:
        raise ValueError(f"{x} does not have the correct format")
    return m.group(1)

def bs_filename_to_hometeam(x:str) -> str:
    m = re.match(r'boxscores_\d{8}0(...)', x)
    if m is None:
        raise ValueError(f"{x} does not have the correct format")
    return m.group(1)


