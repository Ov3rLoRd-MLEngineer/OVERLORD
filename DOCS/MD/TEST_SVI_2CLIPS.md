# Test SVI 2 clips — fusion et validation visuelle (Tâche 1, session 05/08/2026)

Suite à `TEST_SVI_04082026.md` (2 clips SVI 2.0 Pro + ColorMatch LAB, 37 frames
chacun, testés séparément le 2026-08-04/05). Objectif de cette tâche : fusionner
les deux clips en une seule vidéo pour confirmer/infirmer visuellement le
raccord et la perte de netteté rapportée au clip 2.

## Fusion

Sources :
- `D:\Ov3rLoRd AI\ComfyUI\output\Anisora Test\svi_test\svi_clip1_00001.mp4`
- `D:\Ov3rLoRd AI\ComfyUI\output\Anisora Test\svi_test\svi_clip2_00001.mp4`

```
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy svi_74frames_merged.mp4
```

(`-c copy`, pas de ré-encodage — les deux clips partagent déjà le même codec/
résolution/fps, confirmé par `ffprobe` avant fusion : h264, 480x720, 8 fps.)

## Résultat

Output : `D:\OVERLORD\DEMO\output\svi_74frames_merged.mp4`

`ffprobe` sur le fichier fusionné :
- 480x720, 8 fps
- **74 frames exactes** (37 + 37, aucune frame perdue/dupliquée par la fusion)
- Durée 9.25 s

Concaténation techniquement propre (pas d'erreur, pas de désync, compte de
frames exact). Ceci confirme uniquement que la fusion elle-même n'introduit
pas d'artefact — **ne dit rien sur la qualité visuelle du raccord** (drift
colorimétrique, saut de mouvement, netteté clip 2), qui reste à valider à l'œil
par l'utilisateur (Claude Code ne peut pas regarder la vidéo).

## En attente

Validation visuelle utilisateur du raccord et de la netteté clip 2 — décision
bloc 4 du plan d'action (`Desktop/plan d'action.txt`) :
- Raccord acceptable → enchaîner clip 3
- Raccord inacceptable → investiguer motion frame
- Netteté clip 2 trop dégradée → avancer LoRA personnage (étape 2 du plan de
  cohérence temporelle)

Note pour comparaison : l'inspection visuelle *déjà faite* dans
`TEST_SVI_04082026.md` (frames extraites individuellement f0/f18/f36 de chaque
clip) n'avait révélé aucun drift visible sur les échantillons inspectés — cette
fusion permet de revoir le raccord en mouvement continu plutôt que sur des
frames isolées, ce qui peut révéler des artefacts de transition invisibles sur
des frames fixes (à confirmer par la vidéo fusionnée).
