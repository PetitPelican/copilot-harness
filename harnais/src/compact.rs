//! Export explicite vers les profils-rôles et périmètres centralisés.
//! Aucun dossier historique, livrable ou fichier de mémoire n'est déplacé.
use std::path::{Path, PathBuf};
use serde_json::{json, Value};

const DEBUT: &str = "<!-- harnais:role:start -->";
const FIN: &str = "<!-- harnais:role:end -->";

fn lit(p: &Path) -> Result<Option<String>, String> {
    match std::fs::read_to_string(p) {
        Ok(t) => Ok(Some(t)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("{} : {e}", p.display())),
    }
}

fn relatif(p: &Path, racine: &Path) -> String {
    if p == racine { return ".".into(); }
    p.strip_prefix(racine).unwrap_or(p).components()
        .map(|c| c.as_os_str().to_string_lossy().to_string()).collect::<Vec<_>>().join("/")
}

fn prepare(p: &Path) -> Result<Vec<(PathBuf, String)>, String> {
    let racine = crate::copilot::racine_git(p)?;
    if !racine.join("brain/fact").is_dir() {
        return Err("forme compacte : migrer la mémoire vers brain/ d'abord".into());
    }
    let mut noms: Vec<String> = std::fs::read_dir(racine.join("brain/mind"))
        .map_err(|e| format!("brain/mind : {e}"))?
        .map(|e| e.map_err(|e| e.to_string())).collect::<Result<Vec<_>, _>>()?
        .into_iter().filter(|e| e.path().is_dir())
        .map(|e| e.file_name().to_string_lossy().to_string()).collect();
    noms.sort();
    if noms.is_empty() { return Err("forme compacte : aucune mémoire d'agent ; créer l'équipe d'abord".into()); }
    for (i, n) in noms.iter().enumerate() {
        let slug = crate::agent::nom_de_profil(n);
        if slug.is_empty() || noms[..i].iter().any(|a| crate::agent::nom_de_profil(a) == slug) {
            return Err(format!("nom de profil vide ou en collision : {n}"));
        }
        for f in ["state.md", "todo.md"] {
            if !racine.join("brain/mind").join(n).join(f).is_file() {
                return Err(format!("mémoire incomplète : {n}/{f}"));
            }
        }
    }
    let mut ecrits = vec![];
    for n in &noms {
        let profil = crate::agent::profil(&racine, n);
        let ancien = racine.join("agents").join(n);
        let existant = lit(&profil)?;
        let texte = if existant.as_deref().is_some_and(|t| t.contains(DEBUT)) {
            let t = existant.clone().unwrap();
            if !t.contains(FIN) { return Err(format!("{} : rôle compact incomplet", profil.display())); }
            t
        } else {
            let role = lit(&ancien.join("AGENTS.md"))?
                .or(lit(&ancien.join("CLAUDE.md"))?);
            let base = match existant.clone() {
                Some(t) if t.starts_with("---\n") || t.starts_with("---\r\n") => t,
                Some(_) => return Err(format!("{} : frontmatter absent ; réconcilier à la main", profil.display())),
                None => format!("---\nname: {}\ndescription: Agent {n} — rôle et mémoire propres au projet\n---\n",
                    crate::agent::nom_de_profil(n)),
            };
            // Un profil déjà autonome n'a pas besoin d'un ancien AGENTS.md.
            match role {
                Some(role) => format!("{}\n\n{DEBUT}\n{}{FIN}\n", base.trim_end(),
                    if role.ends_with('\n') { role } else { format!("{role}\n") }),
                None if existant.is_some() => base,
                None => return Err(format!("{n} : aucun rôle ni profil à exporter")),
            }
        };
        let mut texte = texte.replace(&format!("agents/{n}/AGENTS.md"), &relatif(&profil, &racine))
            .replace(&format!("agents/{n}/CLAUDE.md"), &relatif(&profil, &racine));
        for a in &noms {
            texte = texte.replace(&format!("agents/{a}/livrables"), &format!("docs/livrables/{a}"));
        }
        let garde = crate::agent::perimetre_compact(&racine, n);
        let source = if garde.exists() { garde.clone() }
            else { ancien.join(".github/copilot/perimetre.json") };
        let mut v: Value = match lit(&source)? {
            Some(t) => serde_json::from_str(&t).map_err(|e| format!("{} : {e}", source.display()))?,
            None => return Err(format!("{} : périmètre source absent ; aucune écriture", source.display())),
        };
        let liste = v.get("deny").and_then(Value::as_array)
            .ok_or_else(|| format!("{} : deny doit être une liste", source.display()))?;
        let mut deny = vec![];
        for x in liste {
            let x = x.as_str().ok_or("deny doit contenir uniquement des chemins")?;
            let chemin = PathBuf::from(x);
            let normalise = if chemin.is_absolute() {
                let c = chemin.canonicalize().unwrap_or(chemin);
                if c.starts_with(&racine) { relatif(&c, &racine) } else { x.to_string() }
            } else { x.replace('\\', "/") };
            if normalise.is_empty() { return Err("chemin deny vide : réconcilier à la main".into()); }
            // L'ancien refus de docs/ devient la liste positive : seul le
            // nouveau dossier de livrables propre pourra s'y écrire.
            if (normalise != "docs" || garde.exists()) && !deny.contains(&normalise) { deny.push(normalise); }
        }
        for a in noms.iter().filter(|a| *a != n) {
            for interdit in [format!("brain/mind/{a}"), format!("docs/livrables/{a}")] {
                if !deny.contains(&interdit) { deny.push(interdit); }
            }
        }
        for interdit in [".github", "brain/fact", "brain/poids.json"] {
            if !deny.iter().any(|s| s == interdit) { deny.push(interdit.into()); }
        }
        if n.eq_ignore_ascii_case("QA") && !deny.iter().any(|s| s == ".") { deny.push(".".into()); }
        v["deny"] = json!(deny);
        if !garde.exists() {
            v["allow"] = if n.eq_ignore_ascii_case("QA") { json!([]) }
                else { json!([format!("brain/mind/{n}"), format!("docs/livrables/{n}")]) };
        } else {
            crate::copilot::lis_allow(&crate::agent::contexte(&racine, n))?;
        }
        for (f, t) in [(profil, texte), (garde, serde_json::to_string_pretty(&v).map_err(|e| e.to_string())? + "\n")] {
            if lit(&f)?.as_deref() != Some(&t) { ecrits.push((f, t)); }
        }
    }
    Ok(ecrits)
}

pub fn main(p: &Path, appliquer: bool) -> i32 {
    let ecrits = match prepare(p) {
        Ok(e) => e,
        Err(e) => { eprintln!("equipe --compact : {e}"); return 1; }
    };
    println!("── Architecture compacte{}", if appliquer { "" } else { " [DRY-RUN]" });
    for (f, texte) in &ecrits {
        println!("\n── {} ──\n{texte}", f.display());
    }
    println!("Les mémoires, docs et anciens dossiers agents/ restent INCHANGÉS. \
Les rôles exportés utilisent docs/livrables/<nom>/ : déplacer les livrables et \
réconcilier les références communes séparément, après accord. \
Les périmètres centralisés deviennent prioritaires. Ne retirer agents/ \
qu'après validation des profils, mémoires et gardes dans une nouvelle session.");
    if appliquer {
        for (f, texte) in ecrits {
            let resultat = std::fs::create_dir_all(f.parent().unwrap())
                .and_then(|_| std::fs::write(&f, texte));
            if let Err(e) = resultat { eprintln!("{} : {e} ; export interrompu", f.display()); return 1; }
        }
    } else { println!("Aucune écriture. Relancer avec --apply pour exporter."); }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn export_compact_preserve_memoire_et_interdiction_globale() {
        let p = std::env::temp_dir().join(format!("compact-export-{}", std::process::id()));
        std::fs::create_dir_all(p.join("brain/fact")).unwrap();
        assert!(std::process::Command::new("git").args(["init", "-q"]).current_dir(&p).status().unwrap().success());
        let p = p.canonicalize().unwrap();
        for n in ["OPS", "QA"] {
            let esprit = p.join("brain/mind").join(n);
            let ancien = p.join("agents").join(n);
            std::fs::create_dir_all(&esprit).unwrap();
            std::fs::create_dir_all(ancien.join(".github/copilot")).unwrap();
            std::fs::write(esprit.join("state.md"), "etat initial").unwrap();
            std::fs::write(esprit.join("todo.md"), "todo initial").unwrap();
            std::fs::write(ancien.join("AGENTS.md"), format!("# {n}\nÉcrire dans agents/{n}/livrables/.\n")).unwrap();
            std::fs::write(ancien.join(".github/copilot/perimetre.json"),
                json!({"deny": [p], "custom": true}).to_string()).unwrap();
        }
        assert_eq!(main(&p, false), 0);
        assert!(!p.join(".github").exists());
        assert_eq!(main(&p, true), 0);
        assert!(prepare(&p).unwrap().is_empty(), "export idempotent");
        for n in ["OPS", "QA"] {
            assert_eq!(std::fs::read_to_string(p.join("brain/mind").join(n).join("state.md")).unwrap(), "etat initial");
            assert!(p.join("agents").join(n).join("AGENTS.md").is_file());
            let contexte = crate::agent::contexte(&p, n);
            let garde: Value = serde_json::from_str(&std::fs::read_to_string(crate::agent::perimetre_compact(&p, n)).unwrap()).unwrap();
            assert_eq!(garde["custom"], true);
            assert!(crate::copilot::lis_deny(&contexte).unwrap().contains(&PathBuf::from(".")));
            assert!(crate::copilot::decision(&json!({"tool_name":"Write","tool_input":{"file_path":p.join("x")}}), &contexte).unwrap().is_some());
        }
        std::fs::remove_dir_all(&p).unwrap();
    }

    #[test]
    fn export_invalide_necrit_rien() {
        let p = std::env::temp_dir().join(format!("compact-invalide-{}", std::process::id()));
        std::fs::create_dir_all(p.join("brain/fact")).unwrap();
        std::fs::create_dir_all(p.join("brain/mind/OPS")).unwrap();
        assert!(std::process::Command::new("git").args(["init", "-q"]).current_dir(&p).status().unwrap().success());
        assert_eq!(main(&p, true), 1);
        assert!(!p.join(".github").exists());
        std::fs::remove_dir_all(&p).unwrap();
    }

    #[test]
    fn profils_sans_dossier_agents_resolvent_memoire_et_gardes() {
        let p = std::env::temp_dir().join(format!("compact-sans-agents-{}", std::process::id()));
        std::fs::create_dir_all(p.join("brain/fact")).unwrap();
        std::fs::create_dir_all(p.join(".github/agents")).unwrap();
        std::fs::create_dir_all(p.join(".github/copilot/perimetres")).unwrap();
        assert!(std::process::Command::new("git").args(["init", "-q"]).current_dir(&p).status().unwrap().success());
        let p = p.canonicalize().unwrap();
        for n in ["OPS", "QA"] {
            let esprit = p.join("brain/mind").join(n);
            std::fs::create_dir_all(&esprit).unwrap();
            std::fs::write(esprit.join("state.md"), "---\nmaj: 2026-10-02\nsante: vert\njalon: essai\n---\n").unwrap();
            std::fs::write(esprit.join("todo.md"), "- [ ] tâche\n").unwrap();
            std::fs::write(crate::agent::profil(&p, n),
                format!("---\nname: {}\n---\nRÔLE-{n}\n", crate::agent::nom_de_profil(n))).unwrap();
            std::fs::write(crate::agent::perimetre_compact(&p, n),
                json!({"allow": if n == "QA" { vec![] } else { vec!["brain/mind/OPS","docs/livrables/OPS"] },
                    "deny": if n == "QA" { vec!["."] } else { vec!["brain/fact","brain/mind/QA","docs/livrables/QA"] }}).to_string()).unwrap();
        }
        let lecture = crate::agent::Lecture { choix: crate::agent::Choix::Agent { nom: "ops".into(), ligne: 1 },
            ..crate::agent::Lecture::vide() };
        let s = crate::agent::resous(&p, lecture);
        assert_eq!(s.actif.as_deref(), Some("OPS"));
        assert_eq!(s.place, Some(p.join("brain/mind/OPS")));
        let r = crate::memoire::resous(s.place.as_ref().unwrap());
        assert_eq!(r.nom_agent, "OPS");
        assert_eq!(r.prefixe_mind, "brain/mind/OPS/");
        assert_eq!(r.mind, s.place);
        assert!(crate::agent::lignes_briefing(&s).1.is_empty(), "profil déjà chargé par le menu");
        let qa = crate::agent::resous(&p, crate::agent::Lecture::vide());
        assert_eq!(qa.actif.as_deref(), Some("QA"));
        assert!(crate::agent::lignes_briefing(&qa).1.iter().any(|s| s == "RÔLE-QA"), "rôle servi au défaut");
        let ecrit = |n: &str, f: &str| crate::copilot::decision(
            &json!({"tool_name":"Write", "tool_input":{"file_path":p.join(f)}}),
            &crate::agent::contexte(&p, n));
        assert!(ecrit("OPS", "docs/livrables/OPS/a.md").unwrap().is_none());
        assert!(ecrit("OPS", "docs/audit/a.md").unwrap().is_some());
        assert!(ecrit("OPS", "code.py").unwrap().is_some());
        assert!(ecrit("OPS", "brain/mind/OPS/todo.md").unwrap().is_none());
        assert!(ecrit("OPS", "brain/mind/QA/todo.md").unwrap().is_some());
        let ops_garde = crate::agent::perimetre_compact(&p, "OPS");
        std::fs::write(&ops_garde, r#"{"deny":[]}"#).unwrap();
        assert!(ecrit("OPS", "docs/livrables/OPS/a.md").is_err(), "allow manquant : refuse");
        std::fs::write(&ops_garde, r#"{"allow":"invalide","deny":[]}"#).unwrap();
        assert!(ecrit("OPS", "docs/livrables/OPS/a.md").is_err(), "allow mal formé : refuse");
        assert!(ecrit("QA", "brain/mind/QA/todo.md").unwrap().is_some());
        let qa_garde = crate::agent::perimetre_compact(&p, "QA");
        std::fs::write(&qa_garde, "invalide").unwrap();
        assert!(ecrit("QA", "x.md").is_err());
        std::fs::remove_file(&qa_garde).unwrap();
        assert!(ecrit("QA", "x.md").is_err(), "compact sans garde : refuse");
        assert!(!p.join("agents").exists());
        std::fs::remove_dir_all(&p).unwrap();
    }

    #[test]
    fn compact_dans_worktree_garde_copie_et_principal() {
        let brut = std::env::temp_dir().join(format!("compact-worktree-{}", std::process::id()));
        std::fs::create_dir_all(brut.join("brain/fact")).unwrap();
        std::fs::create_dir_all(brut.join("brain/mind/OPS")).unwrap();
        std::fs::create_dir_all(brut.join(".github/agents")).unwrap();
        std::fs::create_dir_all(brut.join(".github/copilot/perimetres")).unwrap();
        let git = |args: &[&str]| {
            assert!(std::process::Command::new("git").args(args).current_dir(&brut)
                .env("GIT_AUTHOR_NAME", "test").env("GIT_AUTHOR_EMAIL", "test@example.invalid")
                .env("GIT_COMMITTER_NAME", "test").env("GIT_COMMITTER_EMAIL", "test@example.invalid")
                .status().unwrap().success(), "{args:?}");
        };
        git(&["init", "-q"]);
        std::fs::write(brut.join("brain/fact/base.md"), "faits").unwrap();
        std::fs::write(brut.join("brain/mind/OPS/state.md"), "état").unwrap();
        std::fs::write(brut.join(".github/agents/ops.agent.md"), "---\nname: ops\n---\nrôle").unwrap();
        std::fs::write(brut.join(".github/copilot/perimetres/ops.json"),
            r#"{"allow":["brain/mind/OPS","docs/livrables/OPS"],"deny":["brain/fact"]}"#).unwrap();
        git(&["add", "."]);
        git(&["commit", "-qm", "test"]);
        let copie = std::env::temp_dir().join(format!("compact-worktree-copie-{}", std::process::id()));
        git(&["worktree", "add", "--detach", "-q", copie.to_str().unwrap()]);
        let p = brut.canonicalize().unwrap();
        let w = copie.canonicalize().unwrap();
        let lecture = crate::agent::Lecture { choix: crate::agent::Choix::Agent { nom: "ops".into(), ligne: 1 },
            ..crate::agent::Lecture::vide() };
        let s = crate::agent::resous(&w, lecture);
        assert_eq!(s.place, Some(w.join("brain/mind/OPS")));
        assert_eq!(crate::memoire::resous(s.place.as_ref().unwrap()).mind, s.place);
        for racine in [&p, &w] {
            assert!(crate::copilot::decision(&json!({"tool_name":"Write",
                "tool_input":{"file_path":racine.join("brain/fact/base.md")}}),
                s.place.as_ref().unwrap()).unwrap().is_some());
        }
        git(&["worktree", "remove", "--force", copie.to_str().unwrap()]);
        std::fs::remove_dir_all(&brut).unwrap();
    }
}
