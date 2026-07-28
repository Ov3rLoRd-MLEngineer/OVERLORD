"""
Calibration stereo double camera (S10+ 4K60fps + webcam), prerequis au
tournage mocap mains (cf. handsegnet/pose_capture/LANDMARKS_FORMAT.md,
section "Prochaine etape (calibration stereo double camera)").

Adapte de TemugeB/python_stereo_camera_calibrate (meme methode : damier +
cv.calibrateCamera pour les intrinseques par camera, puis cv.stereoCalibrate
pour R/T extrinseques). Deux differences principales par rapport au script
d'origine :

1. Chaque camera a sa PROPRE resolution/fps (calibration_settings.yaml,
   blocs camera0/camera1) au lieu d'un seul frame_width/frame_height partage
   - necessaire ici car S10+ (4K60) et webcam n'ont pas la meme resolution.
   cv.stereoCalibrate est appele avec CALIB_FIX_INTRINSIC (comme dans le
   script d'origine), ce qui rend le parametre image_size non-utilise pour
   l'initialisation des matrices (deja fixees par la calibration mono de
   chaque camera) - avoir deux resolutions differentes ne pose donc pas de
   probleme mathematique ici.

2. Deux modes de capture de paires stereo (etape 3/4) :
   - "live-pairs"  : les deux flux sont ouverts EN MEME TEMPS dans la meme
     boucle (cas d'origine TemugeB) - necessite que les deux cameras soient
     lisibles en direct par OpenCV au moment de la capture (webcam tethered
     + S10+ tethered en mode webcam via une appli, par ex.).
   - "file-pairs"  : les deux flux sont des fichiers deja enregistres
     INDEPENDAMMENT (cas le plus probable : S10+ enregistre en local puis
     transfere) - la synchronisation se fait par TIMESTAMP (secondes), pas
     par index de frame, car les fps different (30 vs 60) et un meme index
     de frame ne correspond PAS au meme instant reel entre les deux clips.
     Necessite un decalage approximatif mesure au clap (clap_offset_seconds
     dans le yaml) - voir README.md.

A executer avec l'interpreteur du venv isole mediapipe_handpose (deja utilise
par extract_hand_landmarks.py - scipy/pyyaml ajoutes pour ce script, opencv/
numpy deja presents) :

    "C:\\Users\\Ov3rL0rD\\.venvs\\mediapipe_handpose\\Scripts\\python.exe" ^
        calib_stereo.py <commande> [options]

Commandes : validate-config, intrinsics, live-pairs, file-pairs, stereo, check
Voir README.md pour la procedure complete pas a pas.
"""
import argparse
import glob
import os
import sys

import cv2 as cv
import numpy as np
import yaml
from scipy import linalg

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES_DIR = os.path.join(HERE, "frames")
FRAMES_PAIR_DIR = os.path.join(HERE, "frames_pair")
PARAMS_DIR = os.path.join(HERE, "camera_parameters")


# ---------------------------------------------------------------------------
# Reglages
# ---------------------------------------------------------------------------

def load_settings(path):
    if not os.path.exists(path):
        print(f"Fichier de reglages introuvable : {path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    for key in ("camera0", "camera1", "chessboard", "capture"):
        if key not in settings:
            print(f"Cle '{key}' manquante dans {path} - fichier de reglages invalide.")
            sys.exit(1)

    return settings


def resolve_source(value):
    """Un entier (ou une chaine numerique) est traite comme un index de
    peripherique OpenCV live ; toute autre chaine est un chemin/URL passe
    tel quel a cv.VideoCapture (fichier video ou flux reseau)."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return value


def open_capture(cam_cfg):
    source = resolve_source(cam_cfg["source"])
    cap = cv.VideoCapture(source)
    # cap.set() est un no-op silencieux sur un fichier deja enregistre (la
    # resolution/fps du fichier prime) - utile seulement pour un device live.
    cap.set(cv.CAP_PROP_FRAME_WIDTH, cam_cfg["width"])
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, cam_cfg["height"])
    cap.set(cv.CAP_PROP_FPS, cam_cfg["fps"])
    return cap


def checkerboard_objp(chessboard_cfg):
    rows = chessboard_cfg["rows"]
    columns = chessboard_cfg["columns"]
    box_size = chessboard_cfg["box_size_cm"]

    objp = np.zeros((rows * columns, 3), np.float32)
    objp[:, :2] = np.mgrid[0:rows, 0:columns].T.reshape(-1, 2)
    objp *= box_size
    return objp


# ---------------------------------------------------------------------------
# Etape 1-2 : calibration mono (intrinseques) - une camera a la fois
# ---------------------------------------------------------------------------

def capture_mono_frames(cam_name, cam_cfg, capture_cfg, view_only=False):
    """Capture interactive : SPACE pour armer, sauvegarde une frame toutes
    les `cooldown` frames lues. Fonctionne identiquement pour un device live
    (l'utilisateur bouge la mire devant la camera) ou un fichier deja
    enregistre (le fichier defile et des frames sont extraites au fil de la
    lecture - pratique pour le S10+ : filmer ~30s en bougeant la mire, puis
    laisser ce script scruter le clip)."""
    os.makedirs(FRAMES_DIR, exist_ok=True)

    cap = open_capture(cam_cfg)
    if not cap.isOpened():
        print(f"Impossible d'ouvrir la source pour '{cam_name}': {cam_cfg['source']}")
        sys.exit(1)

    view_resize = capture_cfg["view_resize"]
    cooldown_reset = capture_cfg["cooldown"]
    number_to_save = capture_cfg["mono_calibration_frames"]

    cooldown = cooldown_reset
    start = False
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Plus de frames disponibles pour '{cam_name}' "
                  f"({saved_count}/{number_to_save} sauvegardees).")
            break

        frame_small = cv.resize(frame, None, fx=1 / view_resize, fy=1 / view_resize)

        if not start:
            cv.putText(frame_small, "SPACE pour demarrer la capture", (50, 50),
                       cv.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 1)
        else:
            cooldown -= 1
            cv.putText(frame_small, f"Cooldown: {cooldown}", (50, 50),
                       cv.FONT_HERSHEY_COMPLEX, 1, (0, 255, 0), 1)
            cv.putText(frame_small, f"Frames: {saved_count}/{number_to_save}", (50, 100),
                       cv.FONT_HERSHEY_COMPLEX, 1, (0, 255, 0), 1)

            if cooldown <= 0:
                savename = os.path.join(FRAMES_DIR, f"{cam_name}_{saved_count}.png")
                cv.imwrite(savename, frame)
                saved_count += 1
                cooldown = cooldown_reset

        cv.imshow(f"mono - {cam_name}", frame_small)
        k = cv.waitKey(1)
        if k == 27:
            break
        if k == 32:
            start = True
        if saved_count == number_to_save:
            break

    cap.release()
    cv.destroyAllWindows()
    print(f"{saved_count} frames sauvegardees dans {FRAMES_DIR} pour '{cam_name}'.")


def calibrate_intrinsics(cam_name, chessboard_cfg, interactive=True):
    images_names = sorted(glob.glob(os.path.join(FRAMES_DIR, f"{cam_name}_*.png")))
    if not images_names:
        print(f"Aucune frame trouvee pour '{cam_name}' dans {FRAMES_DIR} "
              f"(lance d'abord 'intrinsics --camera {cam_name}').")
        sys.exit(1)

    images = [cv.imread(name, 1) for name in images_names]
    criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 100, 0.001)

    rows = chessboard_cfg["rows"]
    columns = chessboard_cfg["columns"]
    objp = checkerboard_objp(chessboard_cfg)

    width = images[0].shape[1]
    height = images[0].shape[0]

    imgpoints = []
    objpoints = []

    for imname, frame in zip(images_names, images):
        gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
        found, corners = cv.findChessboardCorners(gray, (rows, columns), None)

        if not found:
            print(f"  [!] mire non detectee, frame ignoree : {imname}")
            continue

        corners = cv.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        if interactive:
            annotated = frame.copy()
            cv.drawChessboardCorners(annotated, (rows, columns), corners, found)
            cv.putText(annotated, 'Si mauvaise detection, "s" pour ignorer', (25, 25),
                       cv.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 1)
            cv.imshow("intrinsics", annotated)
            k = cv.waitKey(0)
            if k & 0xFF == ord("s"):
                print(f"  ignoree manuellement : {imname}")
                continue

        objpoints.append(objp)
        imgpoints.append(corners)

    if interactive:
        cv.destroyAllWindows()

    if len(objpoints) < 5:
        print(f"Seulement {len(objpoints)} frames valides pour '{cam_name}' "
              f"(minimum recommande : ~10). Reprends des frames.")
        sys.exit(1)

    rmse, cmtx, dist, _rvecs, _tvecs = cv.calibrateCamera(
        objpoints, imgpoints, (width, height), None, None)

    print(f"'{cam_name}' - rmse: {rmse:.4f} (bon calibrage: < 0.3)")
    print(f"'{cam_name}' - camera matrix:\n{cmtx}")
    print(f"'{cam_name}' - distortion coeffs: {dist.ravel()}")

    save_intrinsics(cam_name, cmtx, dist)
    return cmtx, dist


def save_intrinsics(cam_name, cmtx, dist):
    os.makedirs(PARAMS_DIR, exist_ok=True)
    out_path = os.path.join(PARAMS_DIR, f"{cam_name}_intrinsics.dat")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("intrinsic:\n")
        for row in cmtx:
            f.write(" ".join(str(v) for v in row) + "\n")
        f.write("distortion:\n")
        f.write(" ".join(str(v) for v in dist.ravel()) + "\n")
    print(f"Ecrit : {out_path}")


def load_intrinsics(cam_name):
    in_path = os.path.join(PARAMS_DIR, f"{cam_name}_intrinsics.dat")
    if not os.path.exists(in_path):
        print(f"Intrinseques introuvables pour '{cam_name}' : {in_path} "
              f"(lance d'abord la commande 'intrinsics').")
        sys.exit(1)

    with open(in_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    cmtx = np.array([[float(v) for v in lines[i].split()] for i in range(1, 4)])
    dist = np.array([float(v) for v in lines[5].split()]).reshape(1, -1)
    return cmtx, dist


# ---------------------------------------------------------------------------
# Etape 3 : capture des paires stereo
# ---------------------------------------------------------------------------

def capture_pairs_live(cfg):
    """Les deux sources sont ouvertes et lues dans la MEME boucle - valable
    seulement si les deux flux sont vraiment "live" au moment de l'execution
    (sinon utiliser 'file-pairs')."""
    os.makedirs(FRAMES_PAIR_DIR, exist_ok=True)

    name0, name1 = cfg["camera0"]["name"], cfg["camera1"]["name"]
    cap0 = open_capture(cfg["camera0"])
    cap1 = open_capture(cfg["camera1"])
    if not cap0.isOpened() or not cap1.isOpened():
        print("Impossible d'ouvrir les deux flux en simultane - si l'une des "
              "deux cameras est un fichier pre-enregistre independant, "
              "utilise la commande 'file-pairs' a la place.")
        sys.exit(1)

    capture_cfg = cfg["capture"]
    view_resize = capture_cfg["view_resize"]
    cooldown_reset = capture_cfg["cooldown"]
    number_to_save = capture_cfg["stereo_calibration_frames"]

    cooldown = cooldown_reset
    start = False
    saved_count = 0

    while True:
        ret0, frame0 = cap0.read()
        ret1, frame1 = cap1.read()
        if not ret0 or not ret1:
            print("Flux interrompu (une des deux cameras n'a plus de frames).")
            break

        frame0_small = cv.resize(frame0, None, fx=1 / view_resize, fy=1 / view_resize)
        frame1_small = cv.resize(frame1, None, fx=1 / view_resize, fy=1 / view_resize)

        if not start:
            cv.putText(frame0_small, "SPACE pour demarrer", (50, 50),
                       cv.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 1)
        else:
            cooldown -= 1
            for f in (frame0_small, frame1_small):
                cv.putText(f, f"Cooldown: {cooldown}", (50, 50),
                           cv.FONT_HERSHEY_COMPLEX, 1, (0, 255, 0), 1)
                cv.putText(f, f"Paires: {saved_count}/{number_to_save}", (50, 100),
                           cv.FONT_HERSHEY_COMPLEX, 1, (0, 255, 0), 1)

            if cooldown <= 0:
                cv.imwrite(os.path.join(FRAMES_PAIR_DIR, f"{name0}_{saved_count}.png"), frame0)
                cv.imwrite(os.path.join(FRAMES_PAIR_DIR, f"{name1}_{saved_count}.png"), frame1)
                saved_count += 1
                cooldown = cooldown_reset

        cv.imshow(f"pair - {name0}", frame0_small)
        cv.imshow(f"pair - {name1}", frame1_small)
        k = cv.waitKey(1)
        if k == 27:
            break
        if k == 32:
            start = True
        if saved_count == number_to_save:
            break

    cap0.release()
    cap1.release()
    cv.destroyAllWindows()
    print(f"{saved_count} paires sauvegardees dans {FRAMES_PAIR_DIR}.")


def capture_pairs_from_files(cfg, auto=False):
    """Les deux sources sont des fichiers enregistres INDEPENDAMMENT.
    Echantillonne des instants candidats par TIMESTAMP (pas par index de
    frame - les fps different) en appliquant clap_offset_seconds, puis
    detecte la mire sur chaque paire candidate et propose une revue visuelle
    (sauf --auto). Voir README.md pour la methode de mesure du clap_offset.
    """
    os.makedirs(FRAMES_PAIR_DIR, exist_ok=True)

    cam0_cfg, cam1_cfg = cfg["camera0"], cfg["camera1"]
    name0, name1 = cam0_cfg["name"], cam1_cfg["name"]
    chessboard_cfg = cfg["chessboard"]
    sync_cfg = cfg["sync"]
    offset = sync_cfg["clap_offset_seconds"]
    interval = sync_cfg["pair_interval_seconds"]
    number_to_save = cfg["capture"]["stereo_calibration_frames"]

    cap0 = open_capture(cam0_cfg)
    cap1 = open_capture(cam1_cfg)
    if not cap0.isOpened() or not cap1.isOpened():
        print("Impossible d'ouvrir les deux fichiers video "
              f"({cam0_cfg['source']} / {cam1_cfg['source']}).")
        sys.exit(1)

    fps0 = cap0.get(cv.CAP_PROP_FPS) or cam0_cfg["fps"]
    fps1 = cap1.get(cv.CAP_PROP_FPS) or cam1_cfg["fps"]
    total0 = cap0.get(cv.CAP_PROP_FRAME_COUNT)
    total1 = cap1.get(cv.CAP_PROP_FRAME_COUNT)
    duration0 = total0 / fps0
    duration1 = total1 / fps1
    # t (timeline camera0) + offset = instant correspondant dans camera1
    t_max = min(duration0, duration1 - offset)

    if t_max <= 0:
        print("Les deux clips ne se recouvrent pas avec ce clap_offset_seconds "
              "- verifie le signe/la valeur du decalage dans le yaml.")
        sys.exit(1)

    criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 100, 0.001)
    rows, columns = chessboard_cfg["rows"], chessboard_cfg["columns"]

    t = 0.0
    saved_count = 0
    candidate_idx = 0
    while t < t_max and saved_count < number_to_save:
        frame_idx0 = round(t * fps0)
        frame_idx1 = round((t + offset) * fps1)

        cap0.set(cv.CAP_PROP_POS_FRAMES, frame_idx0)
        cap1.set(cv.CAP_PROP_POS_FRAMES, frame_idx1)
        ok0, frame0 = cap0.read()
        ok1, frame1 = cap1.read()
        candidate_idx += 1
        t += interval

        if not ok0 or not ok1:
            continue

        gray0 = cv.cvtColor(frame0, cv.COLOR_BGR2GRAY)
        gray1 = cv.cvtColor(frame1, cv.COLOR_BGR2GRAY)
        found0, corners0 = cv.findChessboardCorners(gray0, (rows, columns), None)
        found1, corners1 = cv.findChessboardCorners(gray1, (rows, columns), None)

        if not (found0 and found1):
            continue

        corners0 = cv.cornerSubPix(gray0, corners0, (11, 11), (-1, -1), criteria)
        corners1 = cv.cornerSubPix(gray1, corners1, (11, 11), (-1, -1), criteria)

        if not auto:
            preview0 = frame0.copy()
            preview1 = frame1.copy()
            cv.drawChessboardCorners(preview0, (rows, columns), corners0, found0)
            cv.drawChessboardCorners(preview1, (rows, columns), corners1, found1)
            cv.putText(preview0, f"t={t - interval:.1f}s  SPACE=garder  s=ignorer",
                       (25, 25), cv.FONT_HERSHEY_COMPLEX, 0.8, (0, 0, 255), 1)
            cv.imshow(f"paire - {name0}", preview0)
            cv.imshow(f"paire - {name1}", preview1)
            k = cv.waitKey(0)
            cv.destroyAllWindows()
            if k & 0xFF == ord("s"):
                continue

        cv.imwrite(os.path.join(FRAMES_PAIR_DIR, f"{name0}_{saved_count}.png"), frame0)
        cv.imwrite(os.path.join(FRAMES_PAIR_DIR, f"{name1}_{saved_count}.png"), frame1)
        saved_count += 1

    cap0.release()
    cap1.release()
    print(f"{saved_count} paires sauvegardees dans {FRAMES_PAIR_DIR} "
          f"({candidate_idx} instants candidats examines).")

    if saved_count < number_to_save:
        print(f"[!] Objectif de {number_to_save} paires non atteint - reduis "
              f"pair_interval_seconds ou verifie clap_offset_seconds/l'eclairage.")


# ---------------------------------------------------------------------------
# Etape 4 : calibration stereo (extrinseques R, T)
# ---------------------------------------------------------------------------

def stereo_calibrate(cfg, cmtx0, dist0, cmtx1, dist1, interactive=True):
    name0, name1 = cfg["camera0"]["name"], cfg["camera1"]["name"]
    c0_names = sorted(glob.glob(os.path.join(FRAMES_PAIR_DIR, f"{name0}_*.png")))
    c1_names = sorted(glob.glob(os.path.join(FRAMES_PAIR_DIR, f"{name1}_*.png")))

    if not c0_names or not c1_names or len(c0_names) != len(c1_names):
        print(f"Paires introuvables/incompletes dans {FRAMES_PAIR_DIR} "
              f"({len(c0_names)} pour '{name0}', {len(c1_names)} pour '{name1}').")
        sys.exit(1)

    c0_images = [cv.imread(n, 1) for n in c0_names]
    c1_images = [cv.imread(n, 1) for n in c1_names]

    criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 100, 0.001)
    chessboard_cfg = cfg["chessboard"]
    rows, columns = chessboard_cfg["rows"], chessboard_cfg["columns"]
    objp = checkerboard_objp(chessboard_cfg)

    # Sert uniquement a initialiser cv.stereoCalibrate ; sans effet reel ici
    # puisque CALIB_FIX_INTRINSIC fixe deja cmtx0/cmtx1 (cf. docstring module).
    width, height = c0_images[0].shape[1], c0_images[0].shape[0]

    imgpoints_left, imgpoints_right, objpoints = [], [], []

    for frame0, frame1 in zip(c0_images, c1_images):
        gray0 = cv.cvtColor(frame0, cv.COLOR_BGR2GRAY)
        gray1 = cv.cvtColor(frame1, cv.COLOR_BGR2GRAY)
        found0, corners0 = cv.findChessboardCorners(gray0, (rows, columns), None)
        found1, corners1 = cv.findChessboardCorners(gray1, (rows, columns), None)

        if not (found0 and found1):
            continue

        corners0 = cv.cornerSubPix(gray0, corners0, (11, 11), (-1, -1), criteria)
        corners1 = cv.cornerSubPix(gray1, corners1, (11, 11), (-1, -1), criteria)

        if interactive:
            preview0, preview1 = frame0.copy(), frame1.copy()
            cv.drawChessboardCorners(preview0, (rows, columns), corners0, found0)
            cv.drawChessboardCorners(preview1, (rows, columns), corners1, found1)
            cv.imshow("img0", preview0)
            cv.imshow("img1", preview1)
            k = cv.waitKey(0)
            if k & 0xFF == ord("s"):
                continue

        objpoints.append(objp)
        imgpoints_left.append(corners0)
        imgpoints_right.append(corners1)

    if interactive:
        cv.destroyAllWindows()

    if len(objpoints) < 5:
        print(f"Seulement {len(objpoints)} paires valides (minimum recommande: ~10).")
        sys.exit(1)

    flags = cv.CALIB_FIX_INTRINSIC
    rmse, cmtx0, dist0, cmtx1, dist1, R, T, _E, _F = cv.stereoCalibrate(
        objpoints, imgpoints_left, imgpoints_right,
        cmtx0, dist0, cmtx1, dist1, (width, height),
        criteria=criteria, flags=flags)

    print(f"stereo rmse: {rmse:.4f} (bon calibrage: < 0.3, acceptable jusqu'a ~0.5)")
    return R, T


def save_extrinsics(name0, name1, R0, T0, R1, T1):
    os.makedirs(PARAMS_DIR, exist_ok=True)

    def _write(name, R, T):
        path = os.path.join(PARAMS_DIR, f"{name}_rot_trans.dat")
        with open(path, "w", encoding="utf-8") as f:
            f.write("R:\n")
            for row in R:
                f.write(" ".join(str(v) for v in row) + "\n")
            f.write("T:\n")
            for row in T:
                f.write(" ".join(str(v) for v in np.atleast_1d(row)) + "\n")
        print(f"Ecrit : {path}")

    _write(name0, R0, T0)
    _write(name1, R1, T1)


# ---------------------------------------------------------------------------
# Etape 5 : verification visuelle (optionnel, necessite les deux cameras live)
# ---------------------------------------------------------------------------

def _make_homogeneous(R, t):
    P = np.zeros((4, 4))
    P[:3, :3] = R
    P[:3, 3] = np.ravel(t)
    P[3, 3] = 1
    return P


def get_projection_matrix(cmtx, R, T):
    return cmtx @ _make_homogeneous(R, T)[:3, :]


def DLT(P1, P2, point1, point2):
    """Triangulation DLT d'un point 3D a partir de ses projections 2D dans
    les deux cameras (point1/point2 en coordonnees PIXELS, pas normalisees -
    cf. LANDMARKS_FORMAT.md : multiplier landmarks_image par la resolution
    de calibration de chaque camera avant triangulation)."""
    A = np.array([
        point1[1] * P1[2, :] - P1[1, :],
        P1[0, :] - point1[0] * P1[2, :],
        point2[1] * P2[2, :] - P2[1, :],
        P2[0, :] - point2[0] * P2[2, :],
    ]).reshape((4, 4))

    B = A.T @ A
    _U, _s, Vh = linalg.svd(B, full_matrices=False)
    return Vh[3, 0:3] / Vh[3, 3]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_validate_config(args):
    cfg = load_settings(args.config)
    for key in ("camera0", "camera1"):
        cam = cfg[key]
        for field in ("name", "source", "width", "height", "fps"):
            if field not in cam:
                print(f"[!] {key}.{field} manquant.")
                sys.exit(1)
    cb = cfg["chessboard"]
    assert cb["rows"] > 0 and cb["columns"] > 0 and cb["box_size_cm"] > 0
    print("Config OK :")
    print(f"  camera0 = {cfg['camera0']['name']} ({cfg['camera0']['width']}x"
          f"{cfg['camera0']['height']}@{cfg['camera0']['fps']}fps, source="
          f"{cfg['camera0']['source']!r})")
    print(f"  camera1 = {cfg['camera1']['name']} ({cfg['camera1']['width']}x"
          f"{cfg['camera1']['height']}@{cfg['camera1']['fps']}fps, source="
          f"{cfg['camera1']['source']!r})")
    print(f"  damier  = {cb['rows']}x{cb['columns']} coins internes, "
          f"case = {cb['box_size_cm']}cm")


def cmd_intrinsics(args):
    cfg = load_settings(args.config)
    cam_cfg = cfg[f"camera{args.camera}"]
    cam_name = cam_cfg["name"]
    if not args.calibrate_only:
        capture_mono_frames(cam_name, cam_cfg, cfg["capture"])
    calibrate_intrinsics(cam_name, cfg["chessboard"], interactive=not args.auto)


def cmd_live_pairs(args):
    cfg = load_settings(args.config)
    capture_pairs_live(cfg)


def cmd_file_pairs(args):
    cfg = load_settings(args.config)
    capture_pairs_from_files(cfg, auto=args.auto)


def cmd_stereo(args):
    cfg = load_settings(args.config)
    name0, name1 = cfg["camera0"]["name"], cfg["camera1"]["name"]
    cmtx0, dist0 = load_intrinsics(name0)
    cmtx1, dist1 = load_intrinsics(name1)

    R, T = stereo_calibrate(cfg, cmtx0, dist0, cmtx1, dist1, interactive=not args.auto)

    R0 = np.eye(3)
    T0 = np.zeros((3, 1))
    save_extrinsics(name0, name1, R0, T0, R, T)
    print("Calibration stereo terminee. Fichiers dans camera_parameters/.")


def cmd_check(args):
    """Etat des lieux de la calibration (aucune camera requise) : quelles
    etapes ont deja produit des fichiers exploitables, et quelle est la
    prochaine commande a lancer. Utile pour reprendre une session sans
    deviner ou on en etait."""
    cfg = load_settings(args.config)
    name0, name1 = cfg["camera0"]["name"], cfg["camera1"]["name"]

    mono_frames = {
        name: len(glob.glob(os.path.join(FRAMES_DIR, f"{name}_*.png")))
        for name in (name0, name1)
    }
    pair_frames = {
        name: len(glob.glob(os.path.join(FRAMES_PAIR_DIR, f"{name}_*.png")))
        for name in (name0, name1)
    }
    intrinsics_ok = {
        name: os.path.exists(os.path.join(PARAMS_DIR, f"{name}_intrinsics.dat"))
        for name in (name0, name1)
    }
    extrinsics_ok = {
        name: os.path.exists(os.path.join(PARAMS_DIR, f"{name}_rot_trans.dat"))
        for name in (name0, name1)
    }

    print(f"camera0 = {name0} ({cfg['camera0']['width']}x{cfg['camera0']['height']}"
          f"@{cfg['camera0']['fps']}fps)")
    print(f"camera1 = {name1} ({cfg['camera1']['width']}x{cfg['camera1']['height']}"
          f"@{cfg['camera1']['fps']}fps)")
    print()
    print("Etape 3 - frames mono capturees :")
    for name in (name0, name1):
        print(f"  {name}: {mono_frames[name]} frame(s)")
    print("Etape 3 - intrinseques calculees :")
    for name in (name0, name1):
        print(f"  {name}: {'OK' if intrinsics_ok[name] else 'manquant'}")
    print("Etape 4 - paires stereo capturees :")
    for name in (name0, name1):
        print(f"  {name}: {pair_frames[name]} frame(s)")
    print("Etape 5 - extrinseques calculees :")
    for name in (name0, name1):
        print(f"  {name}: {'OK' if extrinsics_ok[name] else 'manquant'}")

    print()
    if not all(intrinsics_ok.values()):
        missing = [n for n in (name0, name1) if not intrinsics_ok[n]]
        print(f"Prochaine etape : 'intrinsics --camera 0/1' pour {', '.join(missing)}.")
    elif pair_frames[name0] == 0 or pair_frames[name1] == 0:
        print("Prochaine etape : 'live-pairs' ou 'file-pairs' (capture des paires stereo).")
    elif not all(extrinsics_ok.values()):
        print("Prochaine etape : 'stereo' (calcul R/T a partir des paires deja capturees).")
    else:
        print("Calibration complete (intrinseques + extrinseques presents). "
              "Pret pour la triangulation (cf. LANDMARKS_FORMAT.md).")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=os.path.join(HERE, "calibration_settings.yaml"))
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("validate-config", help="verifie le yaml sans ouvrir de camera")
    sp.set_defaults(func=cmd_validate_config)

    sp = sub.add_parser("intrinsics", help="calibration mono (une camera)")
    sp.add_argument("--camera", choices=["0", "1"], required=True)
    sp.add_argument("--calibrate-only", action="store_true",
                     help="reutilise les frames deja capturees dans frames/, ne recapture pas")
    sp.add_argument("--auto", action="store_true", help="pas de revue visuelle des detections")
    sp.set_defaults(func=cmd_intrinsics)

    sp = sub.add_parser("live-pairs", help="capture simultanee (deux flux live)")
    sp.set_defaults(func=cmd_live_pairs)

    sp = sub.add_parser("file-pairs", help="extraction depuis deux fichiers pre-enregistres")
    sp.add_argument("--auto", action="store_true", help="pas de revue visuelle des paires")
    sp.set_defaults(func=cmd_file_pairs)

    sp = sub.add_parser("stereo", help="calibration stereo (R, T) a partir des paires")
    sp.add_argument("--auto", action="store_true", help="pas de revue visuelle des paires")
    sp.set_defaults(func=cmd_stereo)

    sp = sub.add_parser("check", help="etat des lieux de la calibration (sans camera)")
    sp.set_defaults(func=cmd_check)

    return p


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
