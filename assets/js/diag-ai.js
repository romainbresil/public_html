// ==========================================================================
// --- Scripts Généraux pour le site de Romain Becquart ---
// ==========================================================================

// --- Gestion du menu de navigation sur mobile ---
document.addEventListener('DOMContentLoaded', () => {
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');

    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
        });

        // Ferme le menu en cliquant sur un lien (sauf pour la page ressources)
        mobileMenu.querySelectorAll('a').forEach(link => {
            if (!link.href.includes('ressources.html')) {
                link.addEventListener('click', () => mobileMenu.classList.add('hidden'));
            }
        });
    }

    // --- Gestion des animations à l'apparition au défilement (scroll) ---
    const animatedElements = document.querySelectorAll('.animate-on-scroll');
    if (animatedElements.length > 0) {
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                }
            });
        }, {
            threshold: 0.1
        });
        animatedElements.forEach(element => observer.observe(element));
    }
});


// ==========================================================================
// --- Script pour le Diagnostic IA Conversationnel (Version V1 de l'API) ---
// ==========================================================================

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

// S'assure que les éléments du chatbot existent avant d'ajouter des écouteurs
if (startDiagnosisBtn) {

    // Initialisation de l'historique de la conversation et du nombre max de questions
    let chatHistory = [];
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
            if (result && result.question) {
                chatHistory.push({ role: 'model', parts: [{ text: result.question }] });
                showUserInput(result.question);