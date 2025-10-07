<?php
header('Content-Type: application/json');
// Simule une réponse simple pour voir si le fichier est atteint
$response = ['status' => 'succes', 'message' => 'Le fichier test.php a bien été atteint.'];
echo json_encode($response);
?>