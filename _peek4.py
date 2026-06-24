src=open("agents/director.py",encoding="utf-8").read()
idx=src.find("import")
print(src[idx:idx+300])
