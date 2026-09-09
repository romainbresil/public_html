# Reprise architecte — accès technique Élan Naturel

Décision Romain, 9 septembre 2026 : utiliser prioritairement la boîte GitHub–Netlify pour tous les projets, y compris les nouveaux paquets qualifiés, afin de supprimer les copier-coller VSC/SSH récurrents.

1. Lire la source propriétaire du programme et le contrat `docs/en-v2/architect-access-contract.json` dans `romainbresil/elan-naturel-technical-artifacts`, branche `en-v2-p1-editorial-vertical-completion-2026-09-03`.
2. Lire le manifeste du bridge dans cette ref `elan-vps-bridge-control-v1` et les preuves de capacité actuelles. Une source publiée n'est pas une preuve d'exécution.
3. Émettre une issue `EN-INTENT — …`, label `elan-cms-chatgpt`, selon le contrat `EN_TECHNICAL_MAILBOX_V1` (project_id, mission_id, work_id, request_id, operation, payload). Réutiliser l'identité pour observer un run interrompu; ne pas réémettre aveuglément une mutation.
4. Relire le reçu Netlify et/ou son miroir natif assaini (`mailbox-receipt-gh-issue-N-delivered`), puis la preuve runtime. Le miroir se consulte par generated_artifact_list puis lecture isolée de cet artefact. Conserver attendu/observé/preuve/écart dans la source propriétaire.
5. Le connecteur natif reste observation/secours documenté. SSH est réservé à un amorçage ou secours dont le manque de capacité est établi, après préparation complète du bloc. Ne pas demander des GO techniques répétés dans le mandat.

État à cette publication : transport transversal qualifié CI e5cac7f7faa5b6ea4a791d8af9af3cc5cadc6783 / run34325613658; activation live à prouver. Installation hôte et mise à jour hôte encore en préparation. Runtime VPS observé54, paquet55 qualifié mais non activé. P1 acquise, P2 non ouverte; aucune ancienne migration à rejouer.
