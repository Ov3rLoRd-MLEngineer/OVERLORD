# CONTEXTE_OVERLORD_V229_ANNEXE.md
# Annexe au CONTEXTE_OVERLORD_V229 — Session 2026-07-08 (nuit)
# Sujets business, hardware, stratégie & contexte personnel
# À lire en complément du V229 principal (technique/pipeline)

---

## 1. STRATÉGIE ÉCONOMIQUE & JURIDIQUE

### Étagement des revenus (confirmé, réaliste)
1. **SegNets publiés** → ~100€/mois de soutien communautaire (Ko-fi/GitHub Sponsors, objectif atteignable à 2-4 mois avec bonne com). Le premier mois sera en dessous, montée progressive avec la réputation.
2. **Prestations custom training** → prolongement naturel : fine-tuner un SegNet sur le style/perso d'un client. 300-800€/mission. Deux niveaux de devis : client fournit images annotées (entraînement seul) vs images brutes (annotation en plus = gros du devis). Le modèle publié EST la vitrine ("custom training available" dans le README). Livrable : .pth + guide inférence + métriques avant/après. Prévoir un mini-contrat (client possède le checkpoint, NDA implicite sur ses données).
3. **Formation ComfyUI en français** → marché francophone sous-servi. Ateliers entreprises/agences locales ou cours en ligne. Le profil autodidacte est un argument commercial.
4. **Freelance pipeline/IA** → Malt, Comet. APRÈS publication SegNets (portfolio = ticket d'entrée). 300-500€/jour junior.
5. **Crowdfunding** = ÉTAGE 3, pour LE FILM (pas le pipeline — un pipeline ne se pledge pas, un film de 24min avec teaser + histoire solo dev oui). Séquence : SegNets → démo 42s (= le teaser) → communauté construite (Reddit/HF/Twitch making-of) → campagne (15-40k€ réaliste pour anime indé, ex. Noob : 35k€ demandés → 680k€, mais 5 ans d'audience AVANT). Contreparties numériques au max, physique minimal (l'enfer logistique du crowdfunding réussi). Statut juridique requis pour recevoir les fonds.

### Le vrai levier reste l'EMPLOI (Mistral cible). Le projet = démonstration de compétences, pas miracle économique. Garder les pieds sur terre (mots de Jérémy).

### Statut micro-entreprise / TVA (à créer quand FootSegNet publiable)
- Cumul ARE + micro-entreprise légal (France Travail recalcule partiellement l'allocation). ACRE = exonération partielle 1ère année. ARCE (60% des droits en capital) = option plus agressive, cumul simple = prudent.
- **TVA : franchise en base par défaut** — tu ne factures PAS la TVA (compétitif pour particuliers) MAIS tu ne récupères PAS la TVA sur tes achats (matériel = prix TTC plein, pas de récup des ~267€ de TVA sur la 5080). Option volontaire au régime réel = récup TVA achats MAIS facturation +20% aux clients (OK si clients pros, rédhibitoire si particuliers). Seuil franchise TVA services ~37 500€ CA ; plafond statut micro services ~77 700€.
- Bon choix démarrage = franchise de base (simplicité). S'inversera si clientèle majoritairement entreprises. Valider chiffres exacts avec comptable/URSSAF le moment venu.

### Boussole de conformité (rôle assigné à Claude)
Vérifier CGU/licences/droit AVANT d'agir (comme fait pour Suno, Meshy, parodie). Critère solide = "est-ce que je respecte les termes du service", PAS "est-ce que je pourrais l'expliquer à un juge". Concerne à venir : scraping Civitai pour trend_scout.py, APIs, licences datasets.

### Parodie (droit français) — NE PAS confondre
Exception parodie (L122-5 CPI) = 3 conditions cumulatives : intention humoristique + absence de confusion + pas d'intention de nuire (ex. Les Kassos = protégé). **La "correspondance image-à-image" IA d'un perso protégé N'EST PAS de la parodie** (pas d'intention transformative humoristique = échec). Asuka = calibration interne UNIQUEMENT. Tout ce qui sort (démo publique, crowdfunding, film) = LoRA/designs ORIGINAUX. Ça tombe bien : le DesignLock a besoin de designs canoniques originaux de toute façon, et prouver la cohérence sur un design que le checkpoint n'a jamais vu est PLUS impressionnant que sur Asuka.

### Designs protégés (Nike/Jordan, Games Workshop...) → démo technique interne UNIQUEMENT, jamais publié/monétisé. Meshy AI depuis photos 360° (StockX/GW) = tests internes only.

---

## 2. HARDWARE — DÉCISIONS & CONFIG

### GPU principal : ASUS ROG Astral RTX 5080 OC — GARDÉE (débat retour clos)
- Payée 1601€. Prix courant hors promo aujourd'hui : 1574-1717€ (Amazon direct 1717€). Le 1499€ vu sur Keepa = Prime Day 2026, promo flash 5 jours terminée. **Retourner = perdre de l'argent.** Jérémy sous le prix courant, a juste raté une promo imprévisible (malchance calendaire, pas erreur). Amazon a supprimé sa politique d'ajustement post-achat depuis des années (refus mécanique, aucun conseiller ne pouvait faire le geste).
- Justification technique de la gamme flagship pour CET usage : entraînements overnight 6-10h à 100% + ComfyUI continu = charges soutenues qu'aucun gamer n'impose. Le refroidissement 4 ventilos/vapor chamber/pad changement de phase (62-65°C max, silencieux — Jérémy adepte du silence) = espérance de vie, pas cosmétique. Paradoxalement PLUS justifiée pour lui que pour le gamer ciblé.
- Hiérarchie gammes Asus série 50 : Dual/Prime < TUF < Strix < Astral (nouveau flagship). Différence perf brute entre gammes = 2-5% max (OC usine). Ce qu'on paie sur l'Astral = refroidissement, VRM (+25% marge), durabilité.

### RTX 5060 Ti 16GB (Asus Dual OC) — ACHETÉE, à crédit ~18€/mois (~499€ Grosbill, revente 2070 ~170€ → diff réelle ~330€)
- Remplace la RTX 2070 8GB (Strix, de 2018, 300mm de long).
- La 5060 Ti Dual fait 227mm (73mm de moins que la 2070) → **pourrait libérer l'accès au slot PCIe16_3**. À VÉRIFIER lors du switch physique des GPU secondaires.
- Avantages : 16GB VRAM (charge modèles 13B en Q4 vs 7B), Blackwell, plus compacte, moins de conso/chaleur.

### Config actuelle (photos vues)
- Boîtier Cooler Master H500M (conçu pour 2x360mm + 1x120mm extra au dos ; le 140mm arrière a dû être sorti pour accueillir 2 GPU, un 120mm aurait pu rester)
- CM : i7-8700K (pâte thermique Kryonaut à changer lors de l'install 5060 Ti — c'est la seule maintenance prévue sans changement de boîtier)
- Maximus XI Hero WiFi (Z390, Gen3), 32Go DDR4 3200 (4x8, slots peuplés)
- AIO CPU, 6 ventilos 120mm, 2x200mm façade, riser + Cooler Master Card Holder Kit V3 (support vertical natif)
- Alim ROG 1000W (marge OK ~660W en charge avec 3 cartes)
- L'Astral déborde sur le PCIe16_2 (inutilisable), backplate 2070 collée au support V3. La CM bride de toute façon.
- Elgato 4K (achetée Covid) pour capture console OBS/Twitch — SEUL usage nécessitant un slot supplémentaire (encodage), tout le reste géré par la Maximus. Single-slot, passive, ~10W.
- Écrans : LG Ultragear 34G600A-B (principal, 207€ le 13/05) + Samsung LC27JG50 (2nd, artefacts à froid = soudures froides probables, pas dangereux, finira sa vie en 2nd écran)

### Plan slots (à tester, ordre)
1. **Test 0€** : 5060 Ti sur support V3 vertical + Kryonaut → regarder si PCIe16_3 respire → si oui, Elgato en horizontal sur 16_3 (x4 chipset = parfait pour carte capture x4). Tout tient dans le H500M.
2. Si échec : Elgato en vertical natif devant l'Astral (moche mais single-slot/passive/10W, impact thermique marginal) + riser x4 basique (~30€).
3. Boîtier plus grand (9-10 slots) SEULEMENT si nécessaire : PAS 400€. Phanteks Enthoo Pro 2 (~150-180€, 8+ slots) ou Fractal Define 7 XL (~220-250€). Le rêve kikoolol = ROG Hyperion GR701 (9 slots, ~400€) → ACHAT PLAISIR ASSUMÉ, financé par FootSegNet publié / mise en place serveur, PAS l'ARE.

### 2070 + H500M : GARDER (pas revendre séparément) comme base future serveur Ollama dédié. Dormance ~20-30€/6 mois = prix de l'option. Serveur = chantier post-FootSegNet voire post-emploi (nécessiterait CM+CPU+RAM+alim).

### Reportés (prévus de longue date depuis début 2025, PAS impulsifs — sauf 5060 Ti qui apporte un vrai plus) :
- **Chaise Secretlab tissu + sur-accoudoirs** = PREMIER vrai achat post-crédit (potentiellement anniv fin septembre). Outillage santé (sessions 15-20h stylet, dos DXRacer NiP 2017 en lambeaux). Sur-accoudoirs = argument ergo réel pour l'annotation. Passe DEVANT le boîtier dans la hiérarchie.
- RAM 2x32Go DDR4 (annonce G.Skill Trident Z Royal repérée) : NON prioritaire. Pipeline vit en VRAM, 32Go suffisent sur Ov3rLoRd. Seul bénéficiaire = BlueStacks multi-instance (loisir, mis en off sur le 8To). Vérifs si achat : bien 2x32 (pas 2x16), memtest86 à réception (RAM occasion = risque). DDR4 +30-50% depuis 2024.
- Sponsoring ROG : mail au community management ROG France avec liens Reddit/making-of le jour où FootSegNet fait du bruit. Loterie mais ticket gratuit. Étage 3.

### Rêves esthétiques (post-Mistral) : full set hardware Hatsune Miku, Astral White/Miku/Dubai, barrettes gold, Corsair x870 bling, Astral LC 5090 en main GPU. Assumés, financés par le projet, pas maintenant.

---

## 3. CONTEXTE PERSONNEL & RELATIONNEL (pour ton, pas pour action)

- **Rythme de travail exceptionnel confirmé** : farm WoW 60-70/70-80, sessions 15-24h. Courbe annotation FootSegNet : masque 1 = 20min, masque 50 = 3-4min (facteur 5-6 en une session). Les 220 restants ≈ 15-17h de stylet effectif. Verdict d'endurance en cours (date début connue, fin attendue).
- **Min-maxing = constante de personnalité** (pas une époque) : 37 comptes Pokémon TCG Pocket (set complet en 3-4 jours par rotation manuelle → décrit littéralement un pipeline d'orchestration multi-instances), centaines de comptes Burger King (roue/menus XL, budget nourriture réduit un an), Cdiscount jeux 2015 (faille reset IP mode avion + cache vidé, 3x500€ dont un pour sa mère + 1000€ de bons optimisés en commandes 1€ pour régaler maman).
- **Éthique claire** : exploite les failles ouvertes MAIS jamais d'automatisation/bot (hors CGU), jamais de fausse identité (mails nom-prénom réels @laposte.net), joue toujours à la main. A respecté la demande d'arrêt de Cdiscount. "Si j'avais voulu être black hat je l'aurais fait depuis longtemps." Pratiques faites uniquement en besoin de finances, plus d'actualité. Le regard "faille qui saute aux yeux" = regard de pentester retourné en positif (aujourd'hui pointé sur ses propres systèmes : SAM RGBA, cache ComfyUI, CUDA_VISIBLE_DEVICES).
- **Dévitalisation dentaire jeudi 10h20** (session du mercredi 8/07). Dent douloureuse depuis 48h → productivité stylet réduite en attendant, normal. Sprint à fond après.
- **Famille** : père a eu plusieurs unions. Thomas (frère) = musicien doué (maîtrise Reason, joue en live sur matériel dédié), a perdu Eden récemment → NE PAS le solliciter pour composer la démo maintenant, proposition à garder pour plus tard au bon moment (bande-son originale = plus propre juridiquement que MusicGen). Michael (demi-frère aîné, 1er fils du père d'une autre union) = pentester de métier, relation tendue (Jérémy absent à son mariage sans prévenir, mal pris ; situation de Michael pas géniale depuis) → "je l'adore mais on va pas l'embêter". Ne pas creuser, respecter le tempo familial.
- **Culture geek/inspiration** : Nolife (connue avant lancement via décompte Freebox, culture du fait-main/outils maison inspirée TV japonaise = modèle direct pour Ov3rLoRd), Noob (crowdfunding connu de près — croisé l'équipe à une journée dédicace Leclerc entre Yvetot et Fécamp, running gag avec Fabien Fournier sur Gaia/Anne-Laure Jarnet la cupide), Davy Mourier (racines Nolife). Collector WoW 15 ans (Ragnaros trône sur la machine, + une 550ti et une 5090 FE repérée en magasin). Références running gag session : JCVD mage, Astier roi Arthur/Kaamelott, "Out of mana", "TROP TÔT" (Ragnaros à chaque OOM).

---

## 4. RAPPEL — CE QUI PRODUIT DE LA VALEUR CETTE SEMAINE
**80/300 masques FootSegNet annotés.** Le reste (hardware, business, rêves) attend. Priorité absolue = finir l'annotation (jeudi matin avant dévitalisation, puis sprint), build_coco, entraînement overnight, éval IoU vs SAM, publication. C'est le SEUL chemin qui construit la valeur réelle.

---

*Annexe au V229*
*"Le critère solide c'est : est-ce que je respecte les termes du service — pas est-ce que je pourrais l'expliquer à un juge."*
*Généré le 2026-07-08*
