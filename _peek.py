files=["director.py","agents/clip_validator.py","agents/visual_validator.py","maestro.py"]
for f in files:
    try:
        src=open(f,encoding="utf-8").read()
        print(f"=== {f} ===")
        print(src[:400])
        print("...")
    except Exception as e:
        print(f"ERR {f}: {e}")
