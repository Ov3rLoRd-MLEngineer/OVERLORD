src=open("maestro.py",encoding="utf-8").read()
idx=src.find("ArgumentParser")
print(src[idx:idx+800])
