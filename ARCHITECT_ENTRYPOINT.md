# Reprise architecte — accès technique Élan Naturel

Décision Romain du 9 septembre 2026 : utiliser prioritairement la boîte GitHub–VPS pour tous les projets, nouveaux paquets qualifiés compris, afin de supprimer les copier-coller VSC/SSH récurrents. Les retours techniques ne doivent plus utiliser Netlify Forms : ils consomment le quota des formulaires du site.

1. Lire la source propriétaire et `docs/en-v2/architect-access-contract.json` dans `romainbresil/elan-naturel-technical-artifacts`, branche `en-v2-p1-editorial-vertical-completion-2026-09-03`. Priorité `GITHUB_VPS_MAILBOX`, `netlify_forms_allowed=false`.
2. Lire le manifeste du bridge dans cette ref `elan-vps-bridge-control-v1` et les preuves actuelles. Une source publiée ne prouve pas son exécution.
3. Émettre une issue `EN-INTENT — …`, label `elan-cms-chatgpt`, suivant `EN_TECHNICAL_MAILBOX_V1` : project_id, mission_id, work_id, request_id, operation, payload. Après interruption, observer le même run ; ne pas réémettre aveuglément une mutation.
4. Relire l'artefact assaini `mailbox-receipt-v2-gh-issue-N`, schéma `mailbox-public-receipt-v2`, canal `BROKER_ARTIFACT`. Le connecteur VPS fournit `generated_artifact_list` puis une lecture isolée du contenu exact. Vérifier le run et le runtime. Aucun ACK Netlify n'est requis ; le champ historique n'autorise aucun nouvel envoi Forms.
5. Conserver attendu, observé, preuve et écart dans les sources de mission. Les artefacts du broker ont une rétention limitée ; conserver les preuves utiles dans Git. Les journaux locaux assurent la reprise et l'anti-rejeu.
6. Le connecteur natif sert à lire les reçus et capacités, et au secours documenté. SSH reste réservé à un amorçage ou secours dont le manque de capacité est établi, après préparation complète du bloc. Ne pas redemander un GO technique couvert par le mandat.

État : la voie sans Forms doit être relue après activation du manifeste v3. Les anciennes preuves de transport GitHub–Netlify restent historiques. L'exécuteur hôte est qualifié par CI34328937184 sur source87d84393241f0d708c90a468f45e9720ae33831c, avec vrai install→health→uninstall en CI ; son bootstrap VPS n'est pas installé. Runtime VPS observé54, paquet55 qualifié non activé. P1 acquise, P2 non ouverte. Les objectifs commerciaux ET éditoriaux demeurent dans le mandat.
