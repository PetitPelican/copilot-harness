//! OÙ LE HARNAIS ÉCRIT, ET OÙ IL LIT — le seul endroit qui connaît les chemins.
//!
//! Deux variables décident de tout, et Copilot CLI les pose pour chaque hook
//! de plugin (lu dans le CLI 1.0.90-0, qui les définit par paires) :
//!
//! - `COPILOT_PLUGIN_DATA` : un dossier qui SURVIT AUX MISES À JOUR. C'est là
//!   que vivent les témoins, le journal des blocages, les leçons. Le code se
//!   remplace, pas ce qu'il a appris.
//! - `COPILOT_PLUGIN_ROOT` : où le code est posé. Chemin ABSOLU, ce qui ferme le
//!   piège mesuré du chemin relatif : sur un clone Windows, un lien symbolique
//!   devient un fichier texte et les hooks disparaissent sans bruit.
//!
//! Sans elles, l'état reste dans `~/.copilot/plugin-data/atelier-copilot/harnais`,
//! le dossier que Copilot attribue à ce plugin. Résoudre ce chemin ne crée aucun
//! dossier : seule l'écriture le fait.

use std::path::PathBuf;

/// Le dossier d'état. Voir le module : `COPILOT_PLUGIN_DATA` d'abord.
pub fn socle() -> PathBuf {
    let donnees = ["COPILOT_PLUGIN_DATA", "PLUGIN_DATA"].iter()
        .find_map(|k| std::env::var_os(k).filter(|v| !v.is_empty()));
    chemin_etat(donnees.map(PathBuf::from), crate::hote::maison_copilot())
}

fn chemin_etat(donnees: Option<PathBuf>, maison_copilot: PathBuf) -> PathBuf {
    donnees.unwrap_or_else(|| maison_copilot.join("plugin-data/atelier-copilot/harnais"))
}

/// Le dossier du paquet, ou None hors plugin. Sert à retrouver ce qui est
/// LIVRÉ — les critères de relecture, la liste des rechutes d'origine — par
/// opposition à ce que l'agent a écrit depuis.
pub fn livre() -> Option<PathBuf> {
    crate::copilot::paquet().ok()
}

/// LES NOMS QUE LE SOCLE PRÉVOIT POUR LES FAITS D'UN PROJET — une seule fois.
///
/// Ils décident de trois choses : ce que le briefing indexe, ce que le garde
/// de commit refuse, et ce que la migration exige avant de déplacer quoi que ce
/// soit. Avec TROIS listes séparées, elles s'accorderaient — et c'est
/// exactement le danger : deux copies ne divergent pas quand on les écrit,
/// elles divergent six semaines plus tard, et **rien ne le signale** : chacune
/// continue de répondre, avec aplomb.
///
/// `roles.md` est à part parce qu'il n'existe qu'à PLUSIEURS agents. La
/// migration ne l'exige donc pas ; le garde et le briefing l'acceptent.
pub const FAITS_MONO: &[&str] = &["base.md", "architecture.md", "stack.md", "rules.md"];
pub const FAITS_EQUIPE: &str = "roles.md";

/// Les cinq noms, mono et équipe confondus — ce que le garde autorise.
pub fn faits_tous() -> Vec<&'static str> {
    let mut v = FAITS_MONO.to_vec();
    v.push(FAITS_EQUIPE);
    v
}

#[cfg(test)]
mod essais {

    /// LE CHEMIN ANNONCÉ S'OUVRE DEPUIS OÙ ON TRAVAILLE — les deux sens.
    ///
    /// Le défaut guette : un chemin recomposé à la main au lieu d'être dérivé.
    /// Sous le dossier de travail on
    /// veut du relatif, court et lisible ; en dehors — mémoire déportée — on
    /// veut l'ABSOLU, parce qu'un relatif y serait joli et faux.
    ///
    /// Le second sens compte autant : une fonction qui rendrait toujours
    /// l'absolu passerait le premier cas sans le servir.
    #[test]
    fn le_chemin_annonce_s_ouvre_depuis_ou_on_travaille() {
        let ici = std::path::Path::new("/d/projet/agents/Un Agent");
        // sous le dossier de travail -> relatif
        assert_eq!(chemin_affiche(ici, &ici.join("brain/fact/base.md")),
                   "brain/fact/base.md");
        // en dehors (mémoire déportée) -> absolu, jamais un relatif inventé
        let dehors = std::path::Path::new("/d/projet/memoire/.fact/base.md");
        let rendu = chemin_affiche(ici, dehors);
        assert_eq!(rendu, "/d/projet/memoire/.fact/base.md");
        assert_ne!(rendu, ".fact/base.md", "rend un relatif qui ne s'ouvre pas d'ici");
        // un nom d'agent à espace ne casse rien
        assert_eq!(chemin_affiche(std::path::Path::new("/d/Projet PO"),
                                  std::path::Path::new("/d/Projet PO/x.md")), "x.md");
    }

    use super::*;

    #[test]
    fn les_hooks_et_les_commandes_resolvent_le_meme_etat_copilot_sans_le_creer() {
        let base = std::env::temp_dir().join(format!("etat-copilot-{}", std::process::id()));
        let attendu = base.join("plugin-data/atelier-copilot/harnais");
        assert_eq!(chemin_etat(None, base.clone()), attendu);
        assert!(!attendu.exists(), "la simple résolution ne crée rien");
        let donnees = base.join("donnees-plugin");
        assert_eq!(chemin_etat(Some(donnees.clone()), base.clone()), donnees);
    }
}

/// `json.dumps(x)` DE PYTHON, À L'OCTET. Deux différences avec la sortie
/// compacte de serde, et les deux se voient dans un fichier d'état :
/// Python sépare par `", "` et `": "`, et **échappe tout ce qui n'est pas
/// ASCII** en `\uXXXX`. Un cache écrit par une version et relu par l'autre
/// resterait lisible — mais les deux fichiers ne seraient plus comparables,
/// et c'est la comparaison qui prouve le portage.
pub fn json_python(v: &serde_json::Value) -> String {
    struct Py;
    impl serde_json::ser::Formatter for Py {
        fn begin_array_value<W: ?Sized + std::io::Write>(&mut self, w: &mut W, first: bool)
            -> std::io::Result<()> { if first { Ok(()) } else { w.write_all(b", ") } }
        fn begin_object_key<W: ?Sized + std::io::Write>(&mut self, w: &mut W, first: bool)
            -> std::io::Result<()> { if first { Ok(()) } else { w.write_all(b", ") } }
        fn begin_object_value<W: ?Sized + std::io::Write>(&mut self, w: &mut W)
            -> std::io::Result<()> { w.write_all(b": ") }
        fn write_string_fragment<W: ?Sized + std::io::Write>(&mut self, w: &mut W, f: &str)
            -> std::io::Result<()> {
            for c in f.chars() {
                if (c as u32) < 0x80 { write!(w, "{}", c)?; }
                else {
                    let mut b = [0u16; 2];
                    for u in c.encode_utf16(&mut b) { write!(w, "\\u{:04x}", u)?; }
                }
            }
            Ok(())
        }
    }
    use serde::Serialize;
    let mut buf = Vec::new();
    let mut ser = serde_json::Serializer::with_formatter(&mut buf, Py);
    if v.serialize(&mut ser).is_err() { return String::new(); }
    String::from_utf8(buf).unwrap_or_default()
}

/// COMMENT ON NOMME UN FICHIER À UN AGENT — une seule règle, partout.
///
/// Relatif au dossier d'où il travaille quand le fichier y est accessible ;
/// ABSOLU sinon. Séparateurs en `/` : convention de l'atelier, et sur Windows
/// `display()` rendrait des antislashs.
///
/// POURQUOI CETTE FONCTION EXISTE, et pourquoi elle est ici plutôt que dans un
/// module. Le défaut guette dans chaque module, toujours de la même façon : un
/// chemin recomposé à la main au lieu d'être dérivé de celui qu'on a déjà.
///   · la fin de tour annoncerait `.mind/todo.md` sur un projet en `brain/` —
///     un agent le suivrait, se heurterait à un refus d'écriture, et perdrait
///     son tour sans rien noter ;
///   · le briefing servirait aux agents d'un projet à mémoire déportée un
///     index de fichiers avec TROIS bases implicites, dont aucune ne serait
///     leur dossier de travail : `cat .fact/base.md` n'y trouve rien.
/// Deux chemins qui se recomposent séparément divergent le jour où la forme
/// change, et rien ne le signale — le message reste parfaitement lisible.
pub fn chemin_affiche(depuis: &std::path::Path, cible: &std::path::Path) -> String {
    cible.strip_prefix(depuis)
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| cible.display().to_string())
        .replace('\\', "/")
}
