//! LES TROIS NATURES DE LA MÉMOIRE — fait, croyance, expérience — et TOUS les
//! poids qui la font vivre, réunis à un seul endroit.
//!
//! Deux mécanismes y vivent ensemble : la confiance qui bouge avec les
//! résultats, et les natures qui vieillissent chacune à sa vitesse.
//!
//! DEUX AXES, ET ILS NE FONT PAS LE MÊME TRAVAIL.
//!
//! · le NIVEAU (mesuré · observé · supposé · dit) dit COMMENT une entrée a été
//!   établie : il fixe d'où part sa confiance ;
//! · la NATURE dit CE QU'ELLE EST : elle fixe à quelle vitesse elle vieillit —
//!   une croyance deux fois plus vite qu'un fait, une expérience une fois et
//!   demie moins vite.
//!
//! Un seul point de contact, et il est de définition : UNE SUPPOSITION EST UNE
//! CROYANCE, où qu'elle soit posée. Déclarer « fait » sur une supposition ne la
//! fait pas vieillir moins vite : on ne sort de la pente rapide que par une
//! mesure, jamais par une étiquette.
//!
//! LA NATURE NE SE DEVINE PAS, ET ELLE SE DÉCLARE RAREMENT :
//! · le type d'une note ne se traduit pas en nature — les « consignes » sont
//!   surtout des leçons mesurées, les « références » des faits d'environnement.
//!   En tirer la nature serait un classement automatique, et on sait ce qu'il
//!   vaut : il rend « mesuré » presque partout ;
//! · un axe déclaré à la main s'effondre de lui-même : presque toutes les
//!   notes qui portent un niveau disent « mesuré ».
//!
//! La nature vient donc d'abord de la MAISON, dont c'est déjà la règle écrite :
//! les faits du projet et les leçons de méthode — établies par une mesure —
//! tiennent des faits ; le carnet d'équipe, qui consigne ce qu'un agent a fait,
//! tient des expériences. Une entrée ne déclare sa nature que pour contredire
//! sa maison, et le rapport dit toujours d'où vient celle qu'il affiche.
//!
//! Les traces datées et l'état d'un agent n'ont PAS de maison ici : rien ne les
//! fait vieillir aujourd'hui, et une maison sans lecteur n'a pas de poids à
//! porter. Elles en recevront une le jour où quelque chose les servira.
//!
//! LA NATURE MULTIPLIE DES DURÉES, JAMAIS UN CHIFFRE. Partout où quelque chose
//! vieillit — le délai d'endormissement d'une note, le délai d'oubli d'une
//! entrée de carnet, la péremption d'un fait —, c'est ce délai qu'elle étire ou
//! raccourcit. Le résultat, lui, fait bouger la confiance de la même façon
//! quelle que soit la nature : une entrée lue puis démentie a mal guidé, fait
//! ou croyance.

use crate::carnet::sansaccents;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Nature { Fait, Croyance, Experience }

/// D'où vient la nature affichée — le rapport le dit toujours : une nature
/// tirée de la maison n'a pas le poids d'une nature que l'auteur a posée.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Origine { Supposition, Declaree, Maison }

/// Les maisons dont quelque chose fait vieillir le contenu.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Maison { Faits, Carnet }

impl Nature {
    /// Le multiplicateur des DURÉES.
    pub fn pente(self) -> f64 {
        match self { Nature::Fait => 1.0, Nature::Croyance => 0.5, Nature::Experience => 1.5 }
    }

    /// Un mot déclaré par l'auteur, en français ou en anglais (`fact`,
    /// `belief`). UN MOT INCONNU NE VAUT RIEN : il ne devient pas un fait par
    /// défaut, il laisse la maison décider, comme s'il n'avait pas été écrit.
    pub fn lis(mot: &str) -> Option<Nature> {
        match sansaccents(mot.trim()).as_str() {
            "fait" | "fact" => Some(Nature::Fait),
            "croyance" | "belief" => Some(Nature::Croyance),
            "experience" => Some(Nature::Experience),
            _ => None,
        }
    }
}

pub fn de_la_maison(m: Maison) -> Nature {
    match m { Maison::Faits => Nature::Fait, Maison::Carnet => Nature::Experience }
}

/// La nature d'une entrée, et d'où elle vient. L'ORDRE EST LA RÈGLE : la
/// supposition d'abord (elle est de définition), la déclaration ensuite (elle
/// contredit sa maison), la maison enfin.
pub fn de(maison: Maison, niveau: Option<&str>, declaree: Option<&str>) -> (Nature, Origine) {
    if niveau.map(|n| sansaccents(n.trim()) == "suppose").unwrap_or(false) {
        return (Nature::Croyance, Origine::Supposition);
    }
    if let Some(n) = declaree.and_then(Nature::lis) {
        return (n, Origine::Declaree);
    }
    (de_la_maison(maison), Origine::Maison)
}

/// LA LOI DES QUATRE SEMAINES — « un fait non revérifié depuis 4 semaines est
/// présumé faux ». Règle de la méthode. C'est la durée d'un FAIT ; la nature
/// la gradue.
pub const PEREMPTION_FAIT_J: f64 = 28.0;

pub fn duree(n: Nature, base: f64) -> f64 { base * n.pente() }

// ── d'où part la confiance : le niveau ──────────────────────────────────────

/// Le départ, fixé par le NIVEAU. Un niveau dit QUOI FAIRE pour vérifier, là
/// où un nombre saisi à la main ne dit rien.
///
/// UNE SEULE TABLE pour la fin de tour et le carnet. L'inconnu diverge À
/// DESSEIN : un fait sans niveau pèse un poids inconnu (50), une entrée de
/// carnet est écrite par le hook depuis une tâche cochée — observée par
/// construction (60).
pub fn depart(niveau: &str, maison: Maison) -> i64 {
    match sansaccents(niveau.trim()).as_str() {
        "mesure" => 80,
        "dit" => 85,
        "observe" => 60,
        "suppose" => 40,
        _ => if maison == Maison::Carnet { 60 } else { 50 },
    }
}

// ── ce que le résultat fait à ce qu'on avait lu ─────────────────────────────
//
// Les multiplicateurs du résultat. L'ASYMÉTRIE EST DÉLIBÉRÉE : la confiance
// doit être facile à perdre et lente à reconstruire.

/// Une entrée lue, puis un travail que la vérification confirme — un constat
/// qui TIENT, une tâche aboutie au carnet.
pub const REUSSITE: f64 = 1.03;
/// Une garde a mordu après la lecture : échec MINEUR — un rappel de forme
/// n'est pas un démenti. Sans lecteur jusqu'à ce que `brain/poids.json` porte
/// la confiance des faits.
#[allow(dead_code)]
pub const GARDE: f64 = 0.92;
/// Un constat démenti deux fois de suite : le vrai démenti. Même attente.
#[allow(dead_code)]
pub const DEMENTI: f64 = 0.90;
/// Une tâche que son agent déclare échouée au carnet — le coup le plus dur.
pub const ECHEC_DECLARE: f64 = 0.85;

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn une_supposition_est_une_croyance_ou_qu_elle_soit_posee() {
        for m in [Maison::Faits, Maison::Carnet] {
            assert_eq!(de(m, Some("supposé"), None), (Nature::Croyance, Origine::Supposition));
            assert_eq!(de(m, Some("suppose"), None).0, Nature::Croyance, "sans accent aussi");
            // On ne sort pas de la pente rapide par une étiquette.
            assert_eq!(de(m, Some("supposé"), Some("fait")).0, Nature::Croyance);
        }
    }

    #[test]
    fn la_maison_decide_quand_l_entree_ne_dit_rien() {
        assert_eq!(de(Maison::Faits, Some("mesuré"), None), (Nature::Fait, Origine::Maison));
        assert_eq!(de(Maison::Faits, None, None), (Nature::Fait, Origine::Maison));
        assert_eq!(de(Maison::Carnet, Some("observé"), None), (Nature::Experience, Origine::Maison));
        // TÉMOIN : une fonction qui rendrait « fait » à tout passerait les deux premiers cas.
        assert_ne!(de(Maison::Carnet, None, None).0, de(Maison::Faits, None, None).0);
    }

    #[test]
    fn une_declaration_contredit_sa_maison_et_un_mot_inconnu_ne_vaut_rien() {
        assert_eq!(de(Maison::Faits, Some("mesuré"), Some("croyance")),
                   (Nature::Croyance, Origine::Declaree));
        assert_eq!(de(Maison::Carnet, None, Some("fait")).0, Nature::Fait);
        assert_eq!(de(Maison::Faits, None, Some("Expérience")).0, Nature::Experience);
        assert_eq!(de(Maison::Faits, None, Some("belief")).0, Nature::Croyance, "le mot anglais");
        assert_eq!(de(Maison::Carnet, None, Some("peut-être")), (Nature::Experience, Origine::Maison));
    }

    #[test]
    fn les_pentes_suivent_les_natures() {
        let f = duree(Nature::Fait, PEREMPTION_FAIT_J);
        assert_eq!(f, 28.0, "la loi des quatre semaines");
        assert_eq!(duree(Nature::Croyance, PEREMPTION_FAIT_J), f / 2.0);
        assert_eq!(duree(Nature::Experience, PEREMPTION_FAIT_J), f * 1.5);
    }

    #[test]
    fn le_depart_reunit_les_deux_copies_sans_changer_leurs_valeurs() {
        for m in [Maison::Faits, Maison::Carnet] {
            assert_eq!(depart("mesuré", m), 80);
            assert_eq!(depart("mesure", m), 80);
            assert_eq!(depart("observé", m), 60);
            assert_eq!(depart("supposé", m), 40);
            assert_eq!(depart("dit", m), 85);
        }
        // Le seul endroit où les deux copies divergeaient À DESSEIN : l'inconnu.
        assert_eq!(depart("", Maison::Faits), 50);
        assert_eq!(depart("", Maison::Carnet), 60);
    }

    #[test]
    fn la_confiance_se_perd_plus_vite_qu_elle_ne_se_gagne() {
        for e in [GARDE, DEMENTI, ECHEC_DECLARE] { assert!(e < 1.0 && REUSSITE > 1.0); }
        // La garde est l'échec le plus doux : un rappel de forme n'est pas un démenti.
        assert!(GARDE > DEMENTI && DEMENTI > ECHEC_DECLARE);
        // « Un échec grave coûte cinq réussites. »
        assert!(ECHEC_DECLARE * REUSSITE.powi(5) < 1.0);
    }
}
