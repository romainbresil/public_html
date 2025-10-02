// --- Scripts Généraux ---

// Gestion du menu de navigation sur mobile
const mobileMenuButton = document.getElementById('mobile-menu-button');
const mobileMenu = document.getElementById('mobile-menu');
mobileMenuButton.addEventListener('click', () => mobileMenu.classList.toggle('hidden'));
mobileMenu.querySelectorAll('a').forEach(link => {
    if (!link.href.includes('ressources.html')) {
        link.addEventListener('click', () => mobileMenu.classList.add('hidden'));
    }
});

// Gestion des animations à l'apparition au défilement (scroll)
const animatedElements = document.querySelectorAll('.animate-on-scroll');
const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('is-visible'); });
}, { threshold: 0.1 });
animatedElements.forEach(element => observer.observe(element));

// --- Script pour le Diagnostic IA Conversationnel ---

// Sélection des éléments du DOM
const diagContainer = document.getElementById('diag-container');
const step1Problem = document.getElementById('step1-problem');
const step2Conversation = document.getElementById('step2-conversation');
const startDiagnosisBtn = document.getElementById('start-diagnosis-btn');
const problemDescription = document.getElementById('problem-description');
const chatLog = document.getElementById('chat-log');
const interactionZone = document.getElementById('interaction-zone');
const finalResult = document.getElementById('final-result');
const errorMessage = document.getElementById('error-message');
const resultIndividu = document.getElementById('result-individu');
const resultEquipe = document.getElementById('result-equipe');
const resultOrganisation = document.getElementById('result-organisation');

// Initialisation de l'historique de la conversation et du nombre max de questions
let chatHistory = [];
// --- AMÉLIORATION : Augmentation du nombre de questions pour un diagnostic plus approfondi ---
const MAX_QUESTIONS = 5;

// Événement au clic sur le bouton "Démarrer"
startDiagnosisBtn.addEventListener('click', () => {
    const initialProblem = problemDescription.value;
    if (initialProblem.trim() === '') {
        problemDescription.classList.add('border-red-500');
        problemDescription.placeholder = 'Veuillez décrire votre problématique avant de continuer.';
        return;
    }
    problemDescription.classList.remove('border-red-500');
    chatHistory.push({ role: 'user', parts: [{ text: `Voici la problématique: "${initialProblem}"` }] });
    step1Problem.classList.add('hidden');
    step2Conversation.classList.remove('hidden');
    addMessageToLog(initialProblem, 'user');
    getNextQuestion();
});

// Fonction pour ajouter un message (bulle) dans le chat
function addMessageToLog(message, role) {
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'ai-bubble'}`;
    bubble.textContent = message;
    chatLog.appendChild(bubble);
    chatLog.scrollTop = chatLog.scrollHeight;
}

// Fonction pour afficher l'indicateur de chargement (spinner)
function showSpinner() {
    interactionZone.innerHTML = `<div class="flex justify-center items-center py-4"><div class="spinner"></div><p class="ml-4 text-gray-500 italic">L'IA analyse votre réponse...</p></div>`;
}

// Fonction pour afficher la question de l'IA et le champ de réponse de l'utilisateur
function showUserInput(question) {
    addMessageToLog(question, 'ai');
    interactionZone.innerHTML = `
        <div class="mt-4">
            <label for="user-answer" class="sr-only">Votre réponse</label>
            <textarea id="user-answer" rows="3" class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-bleu-turquoise focus:border-bleu-turquoise" placeholder="Votre réponse..."></textarea>
            <button id="submit-answer-btn" class="mt-4 w-full md:w-auto brand-secondary-bg text-white font-bold py-2 px-6 rounded-lg hover:bg-opacity-90">Répondre</button>
        </div>`;
    document.getElementById('submit-answer-btn').addEventListener('click', handleUserAnswer);
    document.getElementById('user-answer').focus();
}

// Gère la réponse de l'utilisateur
function handleUserAnswer() {
    const userAnswerInput = document.getElementById('user-answer');
    const userAnswer = userAnswerInput.value;
    if (userAnswer.trim() === '') return;
    addMessageToLog(userAnswer, 'user');
    chatHistory.push({ role: 'user', parts: [{ text: userAnswer }] });
    if (chatHistory.filter(m => m.role === 'model').length < MAX_QUESTIONS) {
        getNextQuestion();
    } else {
        getFinalAnalysis();
    }
}

// Fonction asynchrone pour obtenir la prochaine question de l'IA
async function getNextQuestion() {
    showSpinner();
    try {
        const result = await callConversationAPI();
        chatHistory.push({ role: 'model', parts: [{ text: result.question }] });
        showUserInput(result.question);
    } catch (error) { handleError(error); }
}

// Fonction asynchrone pour obtenir l'analyse finale de l'IA
async function getFinalAnalysis() {
    showSpinner();
    try {
        const analysis = await callFinalAnalysisAPI();
        resultIndividu.textContent = analysis.individu;
        resultEquipe.textContent = analysis.equipe;
        resultOrganisation.textContent = analysis.organisation;
        interactionZone.classList.add('hidden');
        finalResult.classList.remove('hidden');
    } catch(error) { handleError(error); }
}

// Gère les erreurs de communication avec l'API
function handleError(error) {
    console.error("Erreur API Gemini:", error);
    step2Conversation.classList.add('hidden');
    errorMessage.classList.remove('hidden');
}

// Prépare le payload pour l'API de conversation
async function callConversationAPI() {
    const systemPrompt = `Tu es un consultant expert, 'Architecte de l'Élan Naturel', menant une conversation de diagnostic pour Romain Becquart. Ton but est de poser ${MAX_QUESTIONS} questions de clarification, UNE PAR UNE. Ton raisonnement s'appuie sur le modèle de Romain : la dynamique 'Élan de Vie' (désir de Lien, Savoir, Harmonie) vs 'Peur Fondamentale'. Tes questions sondent discrètement ces angles. Règles : 1) Ne pose qu'UNE seule question à la fois. 2) N'utilise JAMAIS le jargon du modèle. 3) Tes questions doivent être ouvertes, courtes, empathiques et adaptées à l'historique de la conversation.`;
    const payload = {
        systemInstruction: { parts: [{ text: systemPrompt }] },
        contents: chatHistory,
        generationConfig: { responseMimeType: "application/json", responseSchema: { type: "OBJECT", properties: { "question": { "type": "STRING" } }, required: ["question"] } }
    };
    return await callGeminiAPI(payload);
}

// Prépare le payload pour l'API d'analyse finale
async function callFinalAnalysisAPI() {
    const systemPrompt = `Tu es un consultant expert, 'Architecte de l'Élan Naturel'. Ta mission est de réaliser une analyse finale basée sur une conversation.
    ## Ton Modèle d'Analyse (Interne)
    1.  **Dynamique Centrale :** Tout problème cache une tension entre un 'Élan de Vie' et une 'Peur Fondamentale'.
        * **3 Élans/Désirs :** Lien (types Coeur: 2, 3, 4), Savoir (types Tête: 5, 6, 7), Harmonie (types Instinctif: 8, 9, 1).
        * **3 Peurs :** Non-Reconnaissance (Lien), Monde Contraignant (Savoir), Chaos (Harmonie).
        * **Comportements 'Refuge' :** Actions pour calmer la peur (sur-contrôle, perfectionnisme, etc.).
    2.  **Les 3 Niveaux :** Individu, Équipe, Organisation.
    ## Ta Mission
    1.  **Analyse Interne :** Lis la conversation. Formule une hypothèse sur le profil Ennéagramme probable. Déduis-en l'Élan contrarié, la Peur activée, et les 'comportements refuges' décrits.
    2.  **Restitution Finale :** Produis 3 pistes de réflexion (Individu, Équipe, Organisation). **RÈGLE D'OR :** N'utilise JAMAIS les termes techniques (Ennéagramme, Élan, Peur, etc.). TRADUIS ton analyse en langage simple. Formule des questions ouvertes qui pointent subtilement vers les 'comportements refuges' identifiés. Sois empathique et concis.`;
    const payload = {
        systemInstruction: { parts: [{ text: systemPrompt }] },
        contents: chatHistory,
        generationConfig: {
            responseMimeType: "application/json",
            responseSchema: {
                type: "OBJECT",
                properties: {
                    "individu": { "type": "STRING" },
                    "equipe": { "type": "STRING" },
                    "organisation": { "type": "STRING" }
                },
                required: ["individu", "equipe", "organisation"]
            }
        }
    };
    return await callGeminiAPI(payload);
}

// Fonction générique pour appeler votre proxy PHP qui contacte l'API Gemini
async function callGeminiAPI(payload, retries = 3, delay = 1000) {
    const response = await fetch('gemini-proxy.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!response.ok) {
        const errorBody = await response.json();
        console.error("Détail de l'erreur du proxy:", errorBody);
        throw new Error(`Erreur serveur proxy: ${response.statusText}`);
    }
    const result = await response.json();
    // Gemini retourne parfois une réponse JSON valide mais encapsulée dans la clé "text"
    if (result.candidates && result.candidates[0].content.parts[0].text) {
        try {
            return JSON.parse(result.candidates[0].content.parts[0].text);
        } catch (e) {
            // Si le parsing échoue, ce n'était probablement pas un JSON, on retourne la réponse brute
            return result;
        }
    }
    return result;
}
