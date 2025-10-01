<?php
// Active l'affichage des erreurs pour le débogage (à retirer en production)
ini_set('display_errors', 1);
error_reporting(E_ALL);

// Définit le type de contenu de la réponse comme JSON
header('Content-Type: application/json');

// --- CHARGEMENT SÉCURISÉ DE LA CLÉ API ---
// Le script va chercher le fichier de configuration dans le dossier parent,
// le rendant inaccessible depuis le web.
$configPath = __DIR__ . '/../config.php';

if (!file_exists($configPath)) {
    http_response_code(500);
    echo json_encode(['error' => 'Fichier de configuration introuvable sur le serveur.']);
    exit;
}
require_once $configPath;
$apiKey = GEMINI_API_KEY;
// -----------------------------------------

// Récupère les données envoyées depuis le site (JavaScript)
$input = file_get_contents('php://input');
$data = json_decode($input, true);

// Vérifie si les données sont valides
if (json_last_error() !== JSON_ERROR_NONE || !isset($data['contents'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid JSON input']);
    exit;
}

if ($apiKey === 'VOTRE_CLE_API_GEMINI_ICI' || empty($apiKey)) {
    http_response_code(500);
    echo json_encode(['error' => 'La clé API n\'est pas configurée dans le fichier config.php sur le serveur.']);
    exit;
}

$apiUrl = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key=' . $apiKey;

// Prépare la requête pour l'API Gemini
$options = [
    'http' => [
        'header'  => "Content-Type: application/json\r\n",
        'method'  => 'POST',
        'content' => json_encode($data),
        'ignore_errors' => true // Permet de récupérer le message d'erreur de l'API s'il y en a un
    ]
];

$context  = stream_context_create($options);
$result = file_get_contents($apiUrl, false, $context);

// Récupère les en-têtes de la réponse pour obtenir le code de statut HTTP
$statusCode = (int) explode(' ', $http_response_header[0])[1];

// Renvoie la réponse de l'API Gemini au site web
http_response_code($statusCode);
echo $result;

