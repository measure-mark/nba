import re
def convertMinutes(x:str):
    """ expected usage is
        df["MPC"]=df.MP.apply(convertMinutes)
    """
    m=re.match("(\d{1,3}):(\d{2})", x)
    if m is None:
        return 0
    return float(m.group(1))+ float(m.group(2))/60
