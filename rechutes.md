# Avant d'affirmer

Des questions à rejouer au moment où tu t'apprêtes à dire quelque chose qui
coûtera une décision à @user. Pas avant chaque tour : avant chaque **constat**.

## Mesurer

- **Ton instrument a-t-il répondu à LA question posée, ou à une plus petite ?**
  « ça marche ICI » ne répond pas à « ça marche LÀ-BAS ». Quand tu construis
  l'instrument toi-même : par combien de chemins la chose arrive-t-elle, et
  combien en vois-tu ? Ce qu'un compteur ne voit pas passe pour inexistant —
  dis-le DANS le rapport. **Mais COMPTE les chemins, ne les suppose pas** : un
  plancher annoncé sans preuve est une erreur au même titre qu'un total annoncé
  sans preuve — il a juste l'air prudent.
- **Le chiffre que tu lis mesure-t-il ce que tu crois ?** `unused` n'est pas la
  mémoire libre ; un cache n'est pas le service ; un dépôt n'est pas l'arbre
  qu'une commande a lu.
- **Ton contrôle est-il écrit dans le MÊME SENS que ton constat — et
  teste-t-il ce que le constat AFFIRME ?** Une ligne qui dit « ça manque » et
  une vérification qui demande « est-ce là » rendent TOMBÉ tant que le travail
  reste à faire. Une vérification épinglée sur un CHIFFRE EXACT tombe au
  premier enregistrement de qui que ce soit : le chiffre est un décor, la
  revendication est « il en reste » — vérifie ça, jamais le décor.
- **Un tube n'a-t-il pas avalé le code de sortie de ce qui t'intéressait ?**
  `cmd --exit-status | tail` rend le succès de `tail`. Le pire est
  `| grep motif | tail` : l'échec de `grep` EST l'information.
- **Ton cas limite ressemble-t-il au cas nominal ?** Un cas limite qui
  ressemble au cas nominal court-circuite le garde qui l'attendait : un garde
  qui teste « la liste est-elle vide » laisse passer une liste qui ne contient
  qu'un décor.
- **« Rien vu » : vérifié bon, vérifié mauvais, ou pas mesuré ?** Les trois se
  ressemblent en sortie et ne veulent pas dire la même chose.
- **« Envoyé » n'est pas « arrivé ».** As-tu la preuve du côté qui reçoit ?
- **Ton essai peut-il seulement échouer ?** Un garde `PreToolUse` part AVANT la
  commande et depuis le dossier de l'agent : préparer le cas et le déclencher
  dans le même appel ne teste rien. Poser le cas dans un appel, le déclencher
  dans le suivant, et exiger le témoin négatif. Trois échecs identiques ne sont
  pas une confirmation : c'est un même défaut d'instrument joué trois fois —
  refaire la mesure AUTREMENT avant de conclure.

## Chemins et versions

- **Interroges-tu le chemin qui SERT, ou celui que tu as reconstruit ?** Un
  outil qui recompose l'adresse au lieu de la demander ne sait voir qu'une
  forme, et crie « absent » sur les autres. Demande le chemin à ce qui le
  décide ; un affichage se DÉRIVE du disque, il ne se réécrit pas.
- **De quel arbre parle ta mesure, et lequel la session lit-elle ?** Plusieurs
  copies du même dépôt portent les mêmes noms de fichiers. Et un nom est une
  adresse avant d'être un titre : un renommage déplace en silence ce qui
  s'y range par chemin.
- **Ta référence a-t-elle été rafraîchie, ou compares-tu un instantané au
  présent ?** « Propre » ne veut pas dire « à jour » : un arbre sans aucune
  modification en attente peut accuser des dizaines d'enregistrements de
  retard. Rafraîchir AVANT de comparer deux branches.
- **Corriges-tu la SOURCE, ou la copie que tu es en train de lire ?** Éditer un
  fichier déployé — un cache, un clone de marketplace, une copie de hook —
  fabrique une branche privée que plus rien ne peut avancer. Quand une
  correction publiée « n'arrive pas », remonter dans l'ordre dépôt,
  marketplace, cache, session, au lieu de republier.
- **Ce fait, l'as-tu périmé toi-même en travaillant ?** L'âge n'est pas le seul
  déclencheur : « je viens de changer ce dont ce fait parle » en est un.

## Accès et mécanismes

- **Comptes et jetons — lis-tu l'état du compte, ou un cache ?** Un jeton peut
  vivre hors de tout fichier vérifiable, et « limite de débit », « jeton
  expiré » et « compte déconnecté » se ressemblent en sortie. Seul un démarrage
  réel tranche.
- **Droits — as-tu LU ce droit, ou l'as-tu FRANCHI ?** Une déclaration dans un
  fichier de réglages ne dit rien de ce qui s'exécute. Une API peut répondre
  204 sans rien changer. Le seul contrôle est de faire le geste et de relire
  après.
- **Ce mécanisme a-t-il un appelant, et son déclencheur se produit-il
  vraiment ?** Une étiquette que l'agent doit poser lui-même ne se pose jamais.
  Un garde armé sur **l'action** au lieu du **résultat** se tait pour toujours
  après un seul passage. Un témoin doit avoir **la même durée de vie que ce
  qu'il protège**.

<!-- ÉCRITURE — ce qui suit n'est pas servi à la lecture, c'est la règle du
     fichier lui-même.

     Ce fichier est l'amorce livrée avec le paquet. La copie de l'agent, dans
     le dossier d'état indiqué par `harnais diagnostic`, la remplace dès
     qu'elle existe.

     IL RESTE COURT. Au-delà d'une vingtaine de questions, personne ne le lit,
     et il cesse d'être une liste de contrôle pour devenir un document de plus.
     Ajouter une ligne, c'est en CORRIGER une autre dans le même geste, ou
     n'ajouter rien.

     IL SE CORRIGE SUR PLACE, IL NE S'EMPILE PAS. La même leçon apprise deux
     fois est UNE règle : renforce-la ou précise-la, n'en ajoute pas une seconde
     copie, et n'écris jamais « MISE À JOUR : en fait… » en dessous — corrige la
     phrase qui a induit en erreur.

     CE QU'ON N'Y MET JAMAIS :
     · un nom de personne, de projet, de machine ou de client ;
     · les pannes liées à l'environnement d'un jour — un réseau lent, un service
       en limitation de débit, un jeton expiré ;
     · AUCUNE AFFIRMATION NÉGATIVE SUR UN OUTIL. « X ne marche pas », « on ne
       peut pas faire Y » durcissent en refus qu'on s'oppose à soi-même
       longtemps après que le problème a été réparé ;
     · rien qui ne soit pas rejouable par une question. Une anecdote n'est pas
       un contrôle.
-->
