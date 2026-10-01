// LES RAPPELS D'APPLE, EN DIRECT — la seule partie du harnais écrite en Swift.
//
//     rappels acces                       l'autorisation, en un mot
//     rappels listes                      les noms des listes, séparés par « , »
//     rappels lire <liste>                « 0|1 <tab> titre » par rappel
//     rappels etat <liste>                titres cochés \x1e titres ouverts
//     rappels ecrire <liste> <charge>     crée les rappels du lot, rend leur nombre
//     rappels supprimer <liste> <charge>  efface par titre exact, rend le nombre
//
// POURQUOI SWIFT ICI, ET NULLE PART AILLEURS. Tout le harnais est en Rust, et
// il doit le rester : il tourne aussi sous Windows. Mais les Rappels
// n'existent que sur Mac, et on ne les atteignait qu'en pilotant l'application
// par AppleScript — un passage complet prenait environ une minute, et
// l'application ne sert qu'un client à la fois. Swift est la langue d'Apple :
// il parle directement au magasin des Rappels (EventKit), sans ouvrir
// l'application. La règle : cette seule commande en Swift, tout le reste en
// Rust.
//
// LE CONTRAT EST CELUI DES SCRIPTS D'AVANT, octet pour octet. Le harnais lit
// la sortie exactement comme il lisait celle d'`osascript` : mêmes
// séparateurs, même « rien » pour une liste absente, même nombre rendu. Il n'y
// a donc qu'un seul lecteur, et il n'a pas changé.
//
// TROIS CODES DE SORTIE, et le troisième compte : 0 = fait ; 3 = PAS D'ACCÈS,
// RIEN N'A ÉTÉ TOUCHÉ — le harnais peut alors retenter par l'ancien chemin
// sans risquer un doublon ; tout autre code = échec, que le harnais lit comme
// un échec, jamais comme un succès.
//
// ON NE DEMANDE JAMAIS L'AUTORISATION. Sans écran, la demande ne s'affiche
// pas : elle fait attendre. Si l'accès n'est pas déjà
// accordé, on rend 3 et l'ancien chemin fait ce qu'il faisait.

import EventKit
import Foundation

let SEP_LOT = "\u{1e}"
let SEP_CHAMP = "\u{1f}"

func sortir(_ texte: String) -> Never {
    FileHandle.standardOutput.write(texte.data(using: .utf8) ?? Data())
    exit(0)
}

func echouer(_ texte: String, _ code: Int32) -> Never {
    FileHandle.standardError.write((texte + "\n").data(using: .utf8) ?? Data())
    exit(code)
}

let args = Array(CommandLine.arguments.dropFirst())
let op = args.first ?? ""
let magasin = EKEventStore()

let statut = EKEventStore.authorizationStatus(for: .reminder)
if op == "acces" {
    let mot: String
    switch statut {
    case .fullAccess: mot = "complet"
    case .writeOnly: mot = "ecriture-seule"
    case .denied: mot = "refuse"
    case .restricted: mot = "restreint"
    case .notDetermined: mot = "jamais-demande"
    @unknown default: mot = "inconnu"
    }
    print(mot)
    exit(statut == .fullAccess ? 0 : 3)
}
guard statut == .fullAccess else {
    echouer("rappels : pas d'accès complet aux Rappels — rien n'a été touché", 3)
}

/// La liste de ce nom — la première, comme `list nomListe` en AppleScript.
func liste(_ nom: String) -> EKCalendar? {
    magasin.calendars(for: .reminder).first { $0.title == nom }
}

final class Boite: @unchecked Sendable { var rappels: [EKReminder] = [] }

/// Tous les rappels de la liste, cochés ou non, dans l'ordre de création :
/// l'ordre de l'application n'est pas exposé, et un ordre stable vaut mieux
/// qu'un ordre qui change d'un appel à l'autre.
func rappels(_ l: EKCalendar) -> [EKReminder] {
    let b = Boite()
    let fin = DispatchSemaphore(value: 0)
    magasin.fetchReminders(matching: magasin.predicateForReminders(in: [l])) { r in
        b.rappels = r ?? []
        fin.signal()
    }
    if fin.wait(timeout: .now() + 20) == .timedOut {
        echouer("rappels : le magasin n'a pas répondu en 20 s", 1)
    }
    return b.rappels.sorted {
        ($0.creationDate ?? .distantPast) < ($1.creationDate ?? .distantPast)
    }
}

func besoin(_ i: Int) -> String {
    guard args.count > i else { echouer("rappels \(op) : argument manquant", 2) }
    return args[i]
}

switch op {
case "listes":
    sortir(magasin.calendars(for: .reminder).map { $0.title }.joined(separator: ", ") + "\n")

case "lire":
    guard let l = liste(besoin(1)) else { sortir("\n") }
    let lignes = rappels(l).map { "\($0.isCompleted ? "1" : "0")\t\($0.title ?? "")\n" }
    sortir(lignes.joined() + "\n")

case "etat":
    guard let l = liste(besoin(1)) else { sortir("\n") }
    let tous = rappels(l)
    let faits = tous.filter { $0.isCompleted }.map { $0.title ?? "" }.joined(separator: "\n")
    let ouverts = tous.filter { !$0.isCompleted }.map { $0.title ?? "" }.joined(separator: "\n")
    sortir(faits + SEP_LOT + ouverts + "\n")

case "ecrire":
    let nom = besoin(1)
    let charge = besoin(2)
    let l: EKCalendar
    if let existante = liste(nom) {
        l = existante
    } else {
        guard let source = magasin.defaultCalendarForNewReminders()?.source else {
            echouer("rappels : aucune source où créer la liste « \(nom) »", 1)
        }
        let neuve = EKCalendar(for: .reminder, eventStore: magasin)
        neuve.title = nom
        neuve.source = source
        do { try magasin.saveCalendar(neuve, commit: true) } catch {
            echouer("rappels : la liste « \(nom) » n'a pas pu être créée — \(error)", 1)
        }
        l = neuve
    }
    var n = 0
    for lot in charge.components(separatedBy: SEP_LOT) where !lot.isEmpty {
        let champs = lot.components(separatedBy: SEP_CHAMP)
        guard champs.count == 3 else { continue }
        let r = EKReminder(eventStore: magasin)
        r.calendar = l
        r.title = champs[0]
        r.notes = champs[1]
        // Même échelle qu'AppleScript : 0 aucune, 1 haute, 5 moyenne, 9 basse.
        r.priority = Int(champs[2]) ?? 0
        do { try magasin.save(r, commit: false) } catch {
            echouer("rappels : un rappel n'a pas pu être créé — \(error)", 1)
        }
        n += 1
    }
    do { try magasin.commit() } catch {
        echouer("rappels : l'enregistrement a échoué — \(error)", 1)
    }
    sortir("\(n)\n")

case "supprimer":
    let charge = besoin(2)
    guard let l = liste(besoin(1)) else { sortir("0\n") }
    // PAR TITRE EXACT, comme `whose name is` : tous les rappels qui le portent
    // partent, et on rend combien — un nombre, pas un booléen, pour que le
    // harnais voie un lot à moitié effacé.
    let aOter = Set(charge.components(separatedBy: SEP_LOT))
    var n = 0
    for r in rappels(l) where aOter.contains(r.title ?? "") {
        do { try magasin.remove(r, commit: false) } catch {
            echouer("rappels : un rappel n'a pas pu être effacé — \(error)", 1)
        }
        n += 1
    }
    do { try magasin.commit() } catch {
        echouer("rappels : l'effacement a échoué — \(error)", 1)
    }
    sortir("\(n)\n")

default:
    echouer("rappels : acces | listes | lire <liste> | etat <liste> | ecrire <liste> <charge> | supprimer <liste> <charge>", 2)
}
