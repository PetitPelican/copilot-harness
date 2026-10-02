//! LE HARNAIS — un seul binaire, une sous-commande par hook.
//!
//! Sept hooks vivaient en Python, versionnés nulle part, recopiés à la main.
//! Ils deviennent un paquet unique : une compilation, un artefact, aucun
//! interpréteur à trouver sur la machine d'arrivée. C'est cette dernière ligne
//! qui décide de Windows.
//!
//! LE PORTAGE SE FAIT UN HOOK À LA FOIS, du plus petit au plus gros, et chacun
//! doit rendre EXACTEMENT les mêmes verdicts que sa version Python avant de la
//! remplacer. La valeur de ces hooks n'est pas le code : ce sont les
//! corrections qu'ils encodent, une par brûlure. Les réécrire vite, c'est les
//! perdre sans rien gagner.
//!
//! RÈGLE ABSOLUE, VALABLE POUR TOUTE SOUS-COMMANDE : on sort en 0. Un harnais
//! qui empêche de travailler est un harnais qu'on finit par désarmer. Les seuls
//! blocages volontaires passent par un code 2 explicite, jamais par une panne.

mod adopte;
mod agent;
mod atelier;
mod attente;
mod briefing;
mod carnet;
mod copilot;
mod compact;
mod diagnostic;
mod equipe;
mod hote;
mod journal;
mod memoire;
mod menage;
mod migration;
mod mind_guard;
mod nature;
mod poids;
mod relecture;
mod socle;
mod vue;

use std::io::Read;

/// LA VERSION QUE CE PROGRAMME ANNONCE — une seule source pour tout le code.
/// Un binaire construit à la main dit « -local », ce qui est une information
/// et non un mensonge.
pub fn version_annoncee() -> &'static str {
    option_env!("HARNAIS_VERSION").unwrap_or(concat!(env!("CARGO_PKG_VERSION"), "-local"))
}

fn aide() {
    println!(
        "harnais — le socle agentique\n\n\
         POSER LE HARNAIS SUR UN PROJET — le seul geste à connaître pour démarrer :\n\
         \x20 adopte       pose la mémoire du projet et branche le paquet.\n\
         \x20              `--go` pour écrire · `--equipe A,B,C` à plusieurs\n\
         \x20 brain-migre  déplace une mémoire de l'ancienne organisation vers `brain/`\n\
         \x20 equipe-vue   l'état de tous les projets d'un atelier — terminal ou `--html`\n\
         \x20 equipe       passe un projet en équipe, ou lui ajoute un agent\n\
         \x20              `--agents A,B` · à blanc par défaut · `--apply`\n\
         \x20 atelier-monte  la méthode à la racine, puis le poste du CTO et son harnais\n\
         \x20              à blanc par défaut · `--go` · `--racine R --utilisateur P`\n\
         \x20 menage       caches à supprimer, résidus et mémoires trop grosses à signaler\n\
         \x20              à blanc par défaut · `--apply` · `--racine R` pour un atelier\n\n\
         À LA MAIN, pour comprendre ce que je vois :\n\
         \x20 curateur     la confiance des sections de faits (brain/poids.json), lecture seule\n\
         \x20 resolution   où vit la mémoire de ce dossier (JSON complet)\n\
         \x20 memoire      la même, restreinte — sert à comparer deux versions\n\
         \x20 version      la version du paquet, et l'état du code qui l'a produite\n\n\
         APPELÉES PAR LE HARNAIS (chacune lit sa charge JSON sur l'entrée standard) :\n\
         \x20 journal      PostToolUse/Bash — écrit ce qui a été commité\n\
         \x20 lecture      PostToolUse/Read|Bash — note les sections de faits lues\n\
         \x20 attente   Stop — ce qui attend @user, et les gardes\n\
         \x20 briefing  SessionStart/userPromptTransformed — le briefing d'entrée\n\
         \x20 carnet    lecture du carnet d'équipe (JSON, pour comparer)\n\
         \x20 equipe-amorce  crée le carnet d'équipe — appelé UNE fois, à la conversion\n\
         \x20 mind-guard PreToolUse/Bash — garde les faits et la déclaration d'état\n\
         \x20 perimetre   PreToolUse/Edit|Write — refuse les écritures hors lot\n\
         \x20 relecture    lance le juge sur les demandes en attente\n\
         \x20 diagnostic   ce que je trouve, ce que je ne trouve pas, et par quel shell\n\
         \x20 agent        l'agent actif d'une session : journal lu, règle appliquée (lecture seule)\n\
         \x20 carnet-essai un banc du carnet, pour les contrôles\n\
         \x20 todo-blocs   les blocs du todo tels que la fin de tour les lit (JSON)\n\
         \x20 rappels      la liste Rappels d'un agent, lue comme la fin de tour la lit\n"
    );
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let sous = args.first().map(|s| s.as_str()).unwrap_or("");
    if std::env::var_os("HARNAIS_JUGE").is_some()
        && matches!(sous, "briefing" | "attente" | "mind-guard" | "perimetre" | "journal" | "lecture") { return; }
    match sous {
        "lecture" => {
            let mut t = String::new();
            let _ = std::io::stdin().read_to_string(&mut t);
            poids::main(&hote::prepare_sans_agent(&t));
        }
        "curateur" => std::process::exit(poids::curateur(&args[1..])),
        "journal" => {
            let mut t = String::new();
            let _ = std::io::stdin().read_to_string(&mut t);
            let t = hote::prepare_si_commit(&t);
            journal::main(&t);
        }
        "attente" => {
            let mut t = String::new();
            let _ = std::io::stdin().read_to_string(&mut t);
            let t = hote::prepare(&t);
            attente::main(&t);
        }
        "briefing" => {
            let mut t = String::new();
            let _ = std::io::stdin().read_to_string(&mut t);
            let t = hote::prepare(&t);
            briefing::main(&t);
        }
        "carnet" => carnet::main(&args[1..]),
        // Le seul appel qui CRÉE le carnet. Il n'est pas dans un hook exprès :
        // un projet mono-agent n'a pas d'équipe, et lui fabriquer un carnet
        // vide à chaque tour donnerait un dispositif qui a l'air monté sans
        // que personne l'ait décidé. La conversion en multi-agents (`equipe`)
        // appelle `carnet::amorce` directement ; cette porte-ci n'a plus
        // d'appelant et reste pour la main.
        "equipe-amorce" => {
            let ou = args.get(1).map(std::path::PathBuf::from)
                .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
            match carnet::amorce(&ou) {
                Some(e) => println!("{}", e.display()),
                None => {
                    eprintln!("carnet non amorcé : aucun dépôt trouvé depuis {}", ou.display());
                    std::process::exit(1);
                }
            }
        }
        "carnet-essai" => carnet::essai(&args[1..]),
        "memoire" => memoire::main(&args[1..]),
        "resolution" => std::process::exit(memoire::resolution_json(&args[1..])),
        "todo-blocs" => std::process::exit(attente::todo_blocs(&args[1..])),
        "rappels" => std::process::exit(attente::rappels(&args[1..])),
        "perimetre" => {
            let mut t = String::new();
            let _ = std::io::stdin().read_to_string(&mut t);
            let t = hote::prepare(&t);
            copilot::garde(&t);
        }
        "mind-guard" => {
            let mut t = String::new();
            let _ = std::io::stdin().read_to_string(&mut t);
            let t = hote::prepare_si_commit(&t);
            mind_guard::main(&t);
        }
        "relecture" => relecture::main(&args[1..]),
        // La seule sous-commande qu'on peut lancer sur un poste inconnu sans
        // rien risquer : elle ne modifie rien, et elle dit CE QU'ELLE NE TROUVE
        // PAS autant que ce qu'elle trouve.
        "diagnostic" => diagnostic::main(&args[1..]),
        "agent" => std::process::exit(agent::main(&args[1..])),
        "adopte" => std::process::exit(adopte::main(&args[1..])),
        "menage" => std::process::exit(menage::main(&args[1..])),
        "atelier-monte" => std::process::exit(atelier::main(&args[1..])),
        "equipe" => std::process::exit(equipe::main(&args[1..])),
        "equipe-vue" => std::process::exit(vue::main(&args[1..])),
        "brain-migre" => std::process::exit(migration::main(&args[1..])),
        // LA VERSION PORTE L'EMPREINTE DU CODE QUI L'A PRODUITE. C'est le seul
        // remède au défaut que ce langage apporte : un interpréteur manquant se
        // voit tout de suite, un programme périmé par rapport à son source ne
        // se voit JAMAIS. Construit par la chaîne, il dit d'où il vient ;
        // construit à la main ici, il dit « local », ce qui est déjà une
        // information — et les contrôles comparent alors les empreintes.
        // LA VERSION ANNONCÉE EST CELLE DU PAQUET, pas celle du fichier de
        // compilation. Deux numéros existaient et personne ne les couplait :
        // un paquet `0.1.2` pouvait contenir un programme annonçant
        // `0.1.0`. Un numéro qui ne dit pas ce qui tourne est pire
        // qu'aucun numéro — il a l'air d'une réponse. Construit à la main, il
        // retombe sur celui du fichier de compilation ET le dit.
        "version" | "--version" | "-V" => println!("{} {}",
            option_env!("HARNAIS_VERSION").unwrap_or(concat!(env!("CARGO_PKG_VERSION"), "-local")),
            option_env!("HARNAIS_SOURCE").unwrap_or("local")),
        "-h" | "--help" | "aide" | "" => aide(),
        autre => {
            // On le DIT, mais on ne bloque pas : un hook mal câblé ne doit pas
            // arrêter l'agent, il doit se voir dans le journal de débogage.
            eprintln!("harnais : sous-commande inconnue « {} »", autre);
            std::process::exit(1);
        }
    }
    std::process::exit(0);
}
