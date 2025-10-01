<?php
// SCRIPT DE TRAITEMENT DU FORMULAIRE DE CONTACT AVEC SMTP

// --- 1. INCLUSION DE LA CONFIGURATION ET DE PHPMailer ---
require_once '../config.php';

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

require 'PHPMailer/src/Exception.php';
require 'PHPMailer/src/PHPMailer.php';
require 'PHPMailer/src/SMTP.php';

// --- 2. TRAITEMENT DU FORMULAIRE (NE PAS MODIFIER EN DESSOUS SAUF SI VOUS SAVEZ CE QUE VOUS FAITES) ---

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
        $mail->Host = 'smtp.gmail.com';
        $mail->SMTPAuth = true;
        $mail->Username = EMAIL_EXPEDITEUR_SMTP;
        $mail->Password = MOT_DE_PASSE_APP; // Utilisation de la constante
        $mail->SMTPSecure = 'tls';
        $mail->Port = 587;
        $mail->CharSet = 'UTF-8';

        // Destinataires
        $mail->setFrom(EMAIL_EXPEDITEUR_SMTP, 'Formulaire de Contact');
        $mail->addAddress(EMAIL_DESTINATAIRE);
        $mail->addReplyTo($email_visiteur, $nom);

        // Contenu de l'e-mail
        $mail->isHTML(false);
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
        // Redirection en cas d'erreur
        header("Location: erreur.html");
        exit;
    }
}
?>