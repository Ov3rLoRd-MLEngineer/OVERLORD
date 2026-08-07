"""Audit pur-Python (pas de Blender/GPU) des .vmd sous E:\\Data Demo\\_extracted :
classe chaque fichier en 'dynamic' (animation de corps entier, plusieurs
bones/frames avec amplitude reelle), 'static_pose' (quasi fige) ou
'camera_only' (aucun bone anime, seulement des frames camera). Format VMD
public (Vocaloid Motion Data 0002 = v2, entetes Shift-JIS)."""
import glob
import json
import os
import struct

ROOT = r"E:\Data Demo\_extracted"


def read_cstr_sjis(buf, length):
    raw = buf[:length].split(b"\x00", 1)[0]
    try:
        return raw.decode("shift_jis", errors="replace")
    except Exception:
        return raw.decode("latin1", errors="replace")


def parse_vmd(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 50:
        return {"error": "fichier trop court"}
    sig = data[:30]
    if b"Vocaloid Motion Data" not in sig:
        return {"error": f"signature inconnue: {sig[:20]!r}"}
    is_v2 = b"0002" in sig
    off = 30
    model_name_len = 20 if is_v2 else 10
    off += model_name_len

    def read_u32():
        nonlocal off
        v = struct.unpack_from("<I", data, off)[0]
        off += 4
        return v

    bone_count = read_u32()
    bone_names = set()
    positions = []  # (frame, x,y,z) pour le bone racine/centre si trouve
    max_frame = 0
    rec_size = 111
    for _ in range(bone_count):
        name = read_cstr_sjis(data[off:off + 15], 15)
        frame, x, y, z = struct.unpack_from("<Ifff", data, off + 15)
        bone_names.add(name)
        max_frame = max(max_frame, frame)
        if name in ("センター", "center", "Center", "全ての親"):
            positions.append((frame, x, y, z))
        off += rec_size

    morph_count = read_u32()
    off += morph_count * 23

    camera_count = read_u32()

    amplitude = 0.0
    if len(positions) >= 2:
        xs = [p[1] for p in positions]
        ys = [p[2] for p in positions]
        zs = [p[3] for p in positions]
        amplitude = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 + (max(zs) - min(zs)) ** 2) ** 0.5

    return {
        "bone_frame_count": bone_count,
        "unique_bones": len(bone_names),
        "max_frame": max_frame,
        "camera_frame_count": camera_count,
        "center_amplitude": round(amplitude, 4),
    }


def classify(info):
    if "error" in info:
        return "UNPARSEABLE"
    if info["bone_frame_count"] == 0 and info["camera_frame_count"] > 0:
        return "camera_only"
    if info["bone_frame_count"] == 0:
        return "empty"
    if info["max_frame"] <= 5 or info["unique_bones"] <= 3:
        return "static_pose"
    # Dynamique: pas mal de frames sur pas mal de bones distincts.
    if info["max_frame"] >= 30 and info["unique_bones"] >= 8:
        return "dynamic"
    return "ambiguous"


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "**", "*.vmd"), recursive=True))
    results = []
    for p in files:
        try:
            info = parse_vmd(p)
        except Exception as e:
            info = {"error": str(e)}
        cls = classify(info)
        results.append({"path": p, "class": cls, **info})
        print(f"{cls:14s} {p} {info}")

    counts = {}
    for r in results:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    print("\nRESUME:", json.dumps(counts, ensure_ascii=False))

    out_path = os.path.join("workspace", "scripts", "vmd_audit_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"RESULT: {out_path}")


if __name__ == "__main__":
    main()
