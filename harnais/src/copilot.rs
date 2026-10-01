//! Déclaration locale et périmètre effectif du paquet Copilot.
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const MARCHE: &str = "atelier-copilot";
pub const PAQUET: &str = "harnais@atelier-copilot";

pub fn executable() -> Option<PathBuf> {
    if let Some(p) = std::env::var_os("HARNAIS_COPILOT").filter(|p| !p.is_empty()) {
        return Some(PathBuf::from(p));
    }
    let noms: &[&str] = if cfg!(windows) { &["copilot.exe", "copilot.cmd", "copilot.bat"] } else { &["copilot"] };
    if let Some(path) = std::env::var_os("PATH") {
        for d in std::env::split_paths(&path) {
            if let Some(p) = noms.iter().map(|n| d.join(n)).find(|p| p.is_file()) { return Some(p); }
        }
    }
    #[cfg(windows)]
    if let Some(local) = std::env::var_os("LOCALAPPDATA") {
        return executable_sdk(&PathBuf::from(local).join("github-copilot-sdk/cli"));
    }
    None
}

fn executable_sdk(d: &Path) -> Option<PathBuf> {
    let mut versions: Vec<_> = std::fs::read_dir(d).ok()?.filter_map(Result::ok)
        .filter_map(|e| {
            let nom = e.file_name().to_string_lossy().to_string();
            let base = nom.split('-').next()?;
            let version: Vec<u64> = base.split('.').map(str::parse).collect::<Result<_, _>>().ok()?;
            if version.len() != 3 { return None; }
            let exe = e.path().join("copilot.exe");
            exe.is_file().then_some((version, nom, exe))
        }).collect();
    versions.sort_by(|a, b| (&b.0, &b.1).cmp(&(&a.0, &a.1)));
    versions.into_iter().next().map(|(_, _, p)| p)
}

pub fn paquet() -> Result<PathBuf, String> {
    for k in ["COPILOT_PLUGIN_ROOT", "PLUGIN_ROOT"] {
        if let Some(p) = std::env::var_os(k).filter(|v| !v.is_empty()) {
            return Ok(PathBuf::from(p));
        }
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let bin = exe.parent().ok_or("programme sans dossier parent")?;
    if bin.file_name().is_some_and(|n| n == "bin") {
        return Ok(bin.parent().ok_or("bin sans dossier parent")?.to_path_buf());
    }
    // Le binaire de développement est dans harnais/target/release/.
    for ancetre in exe.ancestors() {
        if ancetre.join(".github/plugin/marketplace.json").is_file() {
            return Ok(ancetre.to_path_buf());
        }
    }
    Err("racine du paquet introuvable : poser COPILOT_PLUGIN_ROOT".into())
}

pub fn reglages(d: &mut Value, racine: &Path) -> Result<(), String> {
    let o = d.as_object_mut().ok_or("settings.json n'est pas un objet")?;
    let mk = o.entry("extraKnownMarketplaces").or_insert_with(|| json!({}));
    let mk = mk.as_object_mut().ok_or("extraKnownMarketplaces n'est pas un objet")?;
    let source = json!({"source": {"source": "directory", "path": racine.to_string_lossy()}});
    if let Some(existant) = mk.get(MARCHE) {
        if existant != &source { return Err(format!("marketplace {MARCHE} déjà déclarée avec une autre source")); }
    } else { mk.insert(MARCHE.into(), source); }
    let ep = o.entry("enabledPlugins").or_insert_with(|| json!({}));
    let ep = ep.as_object_mut().ok_or("enabledPlugins n'est pas un objet")?;
    ep.insert(PAQUET.into(), json!(true));
    Ok(())
}

pub fn racine_git(d: &Path) -> Result<PathBuf, String> {
    let sortie = std::process::Command::new("git").args(["rev-parse", "--show-toplevel"])
        .current_dir(d).output().map_err(|e| format!("git depuis {} : {e}", d.display()))?;
    if !sortie.status.success() {
        return Err(format!("aucune racine Git depuis {} : {}", d.display(),
            String::from_utf8_lossy(&sortie.stderr).trim()));
    }
    let chemin = String::from_utf8_lossy(&sortie.stdout).trim().to_string();
    if chemin.is_empty() { return Err("git n'a pas rendu de racine".into()); }
    let racine = PathBuf::from(chemin);
    Ok(racine.canonicalize().unwrap_or(racine))
}

pub fn settings(d: &Path) -> PathBuf { d.join(".github/copilot/settings.json") }

pub fn avertit_settings_agent(d: &Path) {
    let f = settings(d);
    if f.exists() {
        eprintln!("ATTENTION : {} est ignoré par Copilot (hors racine Git) ; reporter ses réglages à la racine du dépôt, sans écraser ce fichier.", f.display());
    }
}

pub fn ancien_paquet(d: &Path) -> bool {
    std::fs::read_to_string(d.join(".claude/settings.json")).ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .and_then(|v| v.get("enabledPlugins")?.get("harnais@atelier")?.as_bool()) == Some(true)
}

pub fn avertit_ancien(d: &Path) {
    if ancien_paquet(d) {
        eprintln!("ATTENTION : {} déclare encore harnais@atelier ; Copilot lit aussi ce fichier et peut charger cet ancien paquet en doublon.", d.join(".claude/settings.json").display());
    }
}

pub fn perimetre(d: &Path) -> Result<Vec<PathBuf>, String> {
    let p = d.join(".github/copilot/perimetre.json");
    if !p.is_file() { return Ok(Vec::new()); }
    let v: Value = serde_json::from_str(&std::fs::read_to_string(&p).map_err(|e| e.to_string())?)
        .map_err(|e| format!("{} : {e}", p.display()))?;
    let deny = v.get("deny").and_then(Value::as_array).ok_or_else(|| format!("{} : deny doit être une liste", p.display()))?;
    deny.iter().map(|v| v.as_str().map(PathBuf::from).ok_or_else(|| "deny doit contenir des chemins absolus".into()))
        .collect()
}

fn canonique(p: &Path) -> PathBuf {
    if let Ok(c) = p.canonicalize() { return c; }
    let mut courant = p;
    let mut reste = Vec::new();
    while !courant.exists() {
        if let Some(n) = courant.file_name() { reste.push(n.to_os_string()); }
        let Some(parent) = courant.parent() else { return p.to_path_buf(); };
        courant = parent;
    }
    let mut canon = courant.canonicalize().unwrap_or_else(|_| courant.to_path_buf());
    for n in reste.iter().rev() { canon.push(n); }
    canon
}

fn dedans(path: &Path, interdit: &Path) -> bool {
    let path = canonique(path);
    let interdit = canonique(interdit);
    #[cfg(windows)]
    { path.to_string_lossy().to_lowercase() == interdit.to_string_lossy().to_lowercase()
      || path.to_string_lossy().to_lowercase().starts_with(&(interdit.to_string_lossy().to_lowercase() + "\\")) }
    #[cfg(not(windows))]
    { path.starts_with(interdit) }
}

pub fn decision(charge: &Value, lancement: &Path) -> Result<Option<String>, String> {
    let nom = charge.get("tool_name").or_else(|| charge.get("toolName")).and_then(Value::as_str).unwrap_or("");
    if !["Edit", "Write", "edit", "create", "apply_patch", "str_replace_editor"].contains(&nom) { return Ok(None); }
    let denies = perimetre(lancement)?;
    if denies.is_empty() { return Ok(None); }
    let args = charge.get("tool_input").or_else(|| charge.get("toolArgs"));
    let args_texte: Value = match args {
        Some(Value::String(s)) if s.trim_start().starts_with("*** Begin Patch") =>
            json!({"patch": s}),
        Some(Value::String(s)) => serde_json::from_str(s).map_err(|e| format!("arguments de l'outil illisibles : {e}"))?,
        Some(v) => v.clone(), None => return Err("arguments de l'outil absents".into()),
    };
    // Le réglage du plugin vit à la racine Git ; le périmètre reste au lancement de l’agent.
    let depot = racine_git(lancement)?;
    let agent = lancement.canonicalize().unwrap_or_else(|_| lancement.to_path_buf());
    if !agent.starts_with(&depot) { return Err("dossier de lancement hors du dépôt Git".into()); }
    let mut chemins: Vec<&str> = ["file_path", "path", "filePath"]
        .iter().filter_map(|k| args_texte.get(*k).and_then(Value::as_str)).collect();
    if let Some(patch) = args_texte.get("patch").and_then(Value::as_str) {
        for ligne in patch.lines() {
            if let Some(f) = ["*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: "]
                .iter().find_map(|prefixe| ligne.strip_prefix(prefixe)) {
                chemins.push(f.trim());
            }
        }
    }
    if chemins.is_empty() { return Err("outil d'écriture sans chemin vérifiable".into()); }
    for chemin in chemins {
        let chemin = Path::new(chemin);
        let chemin = if chemin.is_absolute() { chemin.to_path_buf() } else { lancement.join(chemin) };
        for interdit in &denies {
            if dedans(&chemin, interdit) {
                return Ok(Some(format!("Écriture refusée hors périmètre : {} (dossier interdit : {})", chemin.display(), interdit.display())));
            }
        }
    }
    Ok(None)
}

pub fn garde(entree: &str) {
    if std::env::var_os("HARNAIS_JUGE").is_some() { return; }
    let charge: Value = match serde_json::from_str(entree) {
        Ok(c) => c, Err(e) => { println!("{}", crate::hote::refus(&format!("charge de garde illisible : {e}"))); return; }
    };
    let lancement = std::env::var_os("COPILOT_PROJECT_DIR")
        .map(PathBuf::from).or_else(|| charge.get("cwd").and_then(Value::as_str).map(PathBuf::from));
    let Some(lancement) = lancement else { println!("{}", crate::hote::refus("dossier de lancement inconnu")); return; };
    match decision(&charge, &lancement) {
        Ok(Some(motif)) | Err(motif) => println!("{}", crate::hote::refus(&motif)),
        Ok(None) => (),
    }
}

#[cfg(test)]
mod essais {
    use super::*;
    #[test]
    fn garde_les_deux_formats_et_la_frontiere() {
        let d = std::env::temp_dir().join(format!("perimetre-copilot-{}", std::process::id()));
        let dossier = d.join("agents/voisin");
        std::fs::create_dir_all(&dossier).unwrap();
        std::process::Command::new("git").args(["init", "-q"]).current_dir(&d).status().unwrap();
        std::fs::create_dir_all(d.join("agents/moi/.github/copilot")).unwrap();
        let moi = d.join("agents/moi");
        std::fs::write(moi.join(".github/copilot/perimetre.json"), json!({"deny":[dossier]}).to_string()).unwrap();
        let dehors = json!({"tool_name":"Write", "tool_input":{"file_path":d.join("agents/voisin/a.rs")}});
        assert!(decision(&dehors, &moi).unwrap().is_some());
        let camel_dehors = json!({"toolName":"create", "toolArgs":{"path":d.join("agents/voisin/b.rs")}});
        assert!(decision(&camel_dehors, &moi).unwrap().is_some());
        let snake_dedans = json!({"tool_name":"Edit", "tool_input":{"file_path":d.join("agents/moi/b.rs")}});
        assert!(decision(&snake_dedans, &moi).unwrap().is_none());
        let patch = json!({"toolName":"apply_patch", "toolArgs":{"patch":format!("*** Begin Patch\n*** Update File: {}\n*** End Patch", d.join("agents/voisin/p.rs").display())}});
        assert!(decision(&patch, &moi).unwrap().is_some());
        let raw = json!({"toolName":"apply_patch", "toolArgs":format!(
            "*** Begin Patch\n*** Update File: {}\n*** Move to: {}\n*** End Patch\n",
            d.join("agents/moi/p.rs").display(), d.join("agents/voisin/p.rs").display())});
        assert!(decision(&raw, &moi).unwrap().is_some());
        assert!(decision(&json!({"toolName":"apply_patch", "toolArgs":"pas du JSON"}), &moi).is_err());
        let dedans = json!({"toolName":"edit", "toolArgs":{"path":d.join("agents/moi/a.rs")}});
        assert!(decision(&dedans, &moi).unwrap().is_none());
        assert!(decision(&json!({"tool_name":"Edit", "tool_input":{"file_path":d.join("agents/voisinage/a.rs")}}), &moi).unwrap().is_none());
        std::fs::remove_dir_all(&d).unwrap();
        assert!(decision(&dehors, &moi).unwrap().is_none(), "sans périmètre : fail-open");
        assert!(decision(&raw, &moi).unwrap().is_none(), "FREEFORM sans périmètre");
    }

    #[test]
    fn sdk_choisit_la_version_numerique_disponible() {
        let d = std::env::temp_dir().join(format!("copilot-sdk-{}", std::process::id()));
        for v in ["1.9.0-0", "1.10.0-0", "autre", "2.0.0-0"] {
            std::fs::create_dir_all(d.join(v)).unwrap();
            if v != "2.0.0-0" { std::fs::write(d.join(v).join("copilot.exe"), "").unwrap(); }
        }
        assert_eq!(executable_sdk(&d), Some(d.join("1.10.0-0/copilot.exe")));
        std::fs::remove_dir_all(d).unwrap();
    }
}
