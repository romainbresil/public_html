<?php
// Active l'affichage des erreurs pour le débogage (à retirer en production)
ini_set('display_errors', 1);
error_reporting(E_ALL);

// Définit le type de contenu de la réponse comme JSON
header('Content-Type: application/json');

// --- CHARGEMENT SÉCURISÉ DE LA CLÉ API ---
$configPath = __DIR__ . '/../config.php';

if (!file_exists($configPath)) {
    http_response_code(500);
    echo json_encode(['error' => 'Fichier de configuration introuvable sur le serveur.']);
    exit;
}
require_once $configPath;
$apiKey = GEMINI_API_KEY;
// -----------------------------------------

$input = file_get_contents('php://input');
$data = json_decode($input, true);

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

$apiUrl = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=' . $apiKey;

// --- Utilisation de cURL pour une meilleure robustesse ---
$ch = curl_init($apiUrl);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
curl_setopt($ch, CURLOPT_TIMEOUT, 30); // Ajout d'un timeout de 30 secondes
curl_setopt($ch, CURLOPT_CAINFO, __DIR__ . '/lib/cacert.pem'); 

$result = curl_exec($ch);
$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlError = curl_error($ch);
curl_close($ch);

// --- Gestion améliorée des erreurs ---
if ($curlError) {
    // Erreur cURL (ex: problème réseau, DNS, SSL)
    http_response_code(500);
    echo json_encode(['error' => 'Erreur de communication serveur-API: ' . $curlError]);
    exit;
}

// Renvoie la réponse de l'API Gemini au site web
http_response_code($statusCode);
echo $result;

?>