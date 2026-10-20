# caveman

Compresse les **réponses** de Copilot, pas les fichiers de mémoire du projet.
La concision ne dispense ni de vérifier un fait ni de signaler « non mesuré ».

```text
/caveman                 mode full (défaut)
/caveman lite            phrases complètes, plus courtes
/caveman ultra           fragments et abréviations non techniques
/caveman wenyan-full     registre classique chinois, sur demande
stop caveman             revenir au style normal
```

Six niveaux sont définis dans [`SKILL.md`](SKILL.md) : `lite`, `full`,
`ultra`, `wenyan-lite`, `wenyan-full`, `wenyan-ultra`. Le mode reste actif
jusqu'au changement ou à la fin de la session ; les avertissements de
sécurité et les opérations irréversibles restent rédigés sans ambiguïté.
