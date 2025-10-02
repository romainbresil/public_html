<?php
// SCRIPT DE TRAITEMENT DU FORMULAIRE DE CONTACT AVEC SMTP

// --- 1. INCLUSION DE LA CONFIGURATION ET DE PHPMailer ---

/*
 * NOTE IMPORTANTE SUR LES CHEMINS D'ACCÈS :
 * Les erreurs précédentes provenaient de chemins incorrects.
 * - Le fichier config.php est recherché dans le dossier PARENT (../) pour des raisons de sécurité.
 * Assurez-vous qu'il se trouve bien à la racine de votre hébergement, à côté de public_html.
 * - Les fichiers PHPMailer sont recherchés dans le dossier 'lib/PHPMailer/src/'.
 *
 * Structure attendue :
 * /
 * |- config.php
 * |- public_html/
 * |- traitement-formulaire.php
 * |- lib/
 * |- PHPMailer/
 * |- src/
 * |- Exception.php
 * |- PHPMailer.php
 * |- SMTP.php
 */

// Inclusion du fichier de configuration (placé en dehors de public_html)
require_once __DIR__ . '/../config.php';

// Inclusion des fichiers de la librairie PHPMailer
use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

require __DIR__ . '/lib/PHPMailer/src/Exception.php';
require __DIR__ . '/lib/PHPMailer/src/PHPMailer.php';
require __DIR__ . '/lib/PHPMailer/src/SMTP.php';

// --- 2. TRAITEMENT DU FORMULAIRE ---

if ($_SERVER["REQUEST_METHOD"] == "POST") {

    // Nettoyage et validation des données
    $nom = htmlspecialchars(trim($_POST["name"]));
    $email_visiteur = htmlspecialchars(trim($_POST["email"]));
    $sujet_besoin = htmlspecialchars(trim($_POST["subject"]));
    $message = htmlspecialchars(trim($_POST["message"]));

    // Validation simple
    if (empty($nom) || empty($message) || !filter_var($email_visiteur, FILTER_VALIDATE_EMAIL)) {
        header("Location: erreur.html");
        exit;
    }

    $mail = new PHPMailer(true);

    try {
        // Paramètres du serveur SMTP
        $mail->isSMTP();
        $mail->Host = 'smtp.gmail.com'; // Ou votre serveur SMTP
        $mail->SMTPAuth = true;
        $mail->Username = EMAIL_EXPEDITEUR_SMTP; // Constante depuis config.php
        $mail->Password = MOT_DE_PASSE_APP; // Constante depuis config.php
        $mail->SMTPSecure = 'tls';
        $mail->Port = 587;
        $mail->CharSet = 'UTF-8';

        // Destinataires
        $mail->setFrom(EMAIL_EXPEDITEUR_SMTP, 'Formulaire Site Web'); // L'expéditeur doit être le même que l'Username
        $mail->addAddress(EMAIL_DESTINATAIRE);    // L'adresse qui reçoit l'e-mail
        $mail->addReplyTo($email_visiteur, $nom); // Pour pouvoir répondre directement au visiteur

        // Contenu de l'e-mail
        $mail->isHTML(false); // E-mail en format texte
        $mail->Subject = "Nouveau message de votre site web de la part de " . $nom;
        $mail->Body = "Nom: " . $nom . "\n"
                      . "Email: " . $email_visiteur . "\n"
                      . "Besoin principal: " . $sujet_besoin . "\n\n"
                      . "Message:\n" . $message;
                      
        $mail->send();
        
        // Redirection en cas de succès
        header("Location: merci.html");
        exit;
    } catch (Exception $e) {
        // En cas d'erreur, on redirige vers la page d'erreur.
        // Pour déboguer, vous pourriez temporairement afficher l'erreur :
        // echo "Message could not be sent. Mailer Error: {$mail->ErrorInfo}";
        header("Location: erreur.html");
        exit;
    }
} else {
    // Si le script est accédé directement sans méthode POST, on redirige.
    header("Location: index.html");
    exit;
}
?>
