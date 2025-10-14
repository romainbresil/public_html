// ==========================================================================
// --- Scripts Généraux pour le site de Romain Becquart ---
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    // --- Gestion du menu de navigation sur mobile ---
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');

    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
        });

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

const diagContainer = document.getElementById('diag-container');
const startDiagnosisBtn = document.getElementById('start-diagnosis-btn');

if (diagContainer && startDiagnosisBtn) {
    const step1Problem = document.getElementById('step1-problem');
    const step2Conversation = document.getElementById('step2-conversation');
    const problemDescription = document.getElementById('problem-description');
    const chatLog = document.getElementById('chat-log');
    const interactionZone = document.getElementById('interaction-zone');
    const finalResult = document.getElementById('final-result');
    const errorMessage = document.getElementById('error-message');
    const resultIndividu = document.getElementById('result-individu');
    const resultEquipe = document.getElementById('result-equipe');
    const resultOrganisation = document.getElementById('result-organisation');

    let chatHistory = [];
    const MAX_QUESTIONS = 5;

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

    function addMessageToLog(message, role) {
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'ai-bubble'}`;
        bubble.textContent = message;
        chatLog.appendChild(bubble);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function showSpinner() {
        interactionZone.innerHTML = `<div class="flex justify-center items-center py-4"><div class="spinner"></div><p class="ml-4 text-gray-500 italic">L'IA analyse votre réponse...</p></div>`;
    }

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

    async function getNextQuestion() {
        showSpinner();
        try {
            const result = await callConversationAPI();
            if (result && result.question) {
                chatHistory.push({ role: 'model', parts: [{ text: JSON.stringify(result) }] });
                showUserInput(result.question);
            } else {
                throw new Error("La réponse de l'API n'a pas le format attendu (question manquante).");
            }
        } catch (error) { handleError(error); }
    }

    async function getFinalAnalysis() {
        showSpinner();
        try {
            const analysis = await callFinalAnalysisAPI();
            if (analysis && analysis.individu && analysis.equipe && analysis.organisation) {
                resultIndividu.textContent = analysis.individu;
                resultEquipe.textContent = analysis.equipe;
                resultOrganisation.textContent = analysis.organisation;
                interactionZone.classList.add('hidden');
                finalResult.classList.remove('hidden');
            } else {
                throw new Error("La réponse de l'API n'a pas le format attendu (analyse finale incomplète).");
            }
        } catch (error) { handleError(error); }
    }

    function handleError(error) {
        console.error("Erreur API Gemini:", error);
        if(step2Conversation) step2Conversation.classList.add('hidden');
        if(errorMessage) errorMessage.classList.remove('hidden');
    }

    // --- Fonctions de préparation des requêtes (Payloads) pour l'API V1 ---

    function callConversationAPI() {
        const systemPrompt = `Tu es un consultant expert. Ton but est de poser ${MAX_QUESTIONS} questions de clarification, UNE PAR UNE. Règles : 1) Ne pose qu'UNE seule question à la fois. 2) N'utilise JAMAIS de jargon. 3) Tes questions doivent être ouvertes, courtes et empathiques. La réponse doit être un JSON avec une clé "question".`;
        const fullHistory = [
            { role: 'user', parts: [{ text: systemPrompt }] },
            { role: 'model', parts: [{ text: '{"question": "Entendu. Quelle est la problématique initiale ?"}' }] }
        ].concat(chatHistory);
        // CORRECTION : Suppression de generationConfig qui n'est pas compatible
        const payload = {
            contents: fullHistory
        };
        return callGeminiAPI(payload);
    }

    function callFinalAnalysisAPI() {
        const systemPrompt = `Tu es un consultant expert. Ta mission est de réaliser une analyse finale basée sur une conversation. Produis un JSON avec 3 pistes de réflexion (clés: "individu", "equipe", "organisation"). N'utilise JAMAIS de jargon technique. Formule des questions ouvertes et empathiques.`;
        const fullHistory = [
            { role: 'user', parts: [{ text: systemPrompt }] },
            { role: 'model', parts: [{ text: '{"individu": "Analyse individuelle prête.", "equipe": "Analyse de l equipe prete.", "organisation": "Analyse organisationnelle prête."}' }] }
        ].concat(chatHistory);
        // CORRECTION : Suppression de generationConfig qui n'est pas compatible
        const payload = {
            contents: fullHistory
        };
        return callGeminiAPI(payload);
    }

    async function callGeminiAPI(payload) {
        const response = await fetch('gemini-proxy.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorBody = await response.json().catch(() => response.text());
            console.error("Erreur détaillée reçue du serveur :", errorBody);
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        if (result.candidates && result.candidates[0].content.parts[0].text) {
             try {
                return JSON.parse(result.candidates[0].content.parts[0].text);
            } catch (e) {
                console.error("Erreur de parsing du JSON de l'API:", e, "Contenu brut :", result.candidates[0].content.parts[0].text);
                throw new Error("La réponse de l'API n'est pas un JSON valide.");
            }
        } else {
             console.error("Réponse inattendue de l'API:", result);
             throw new Error("Format de réponse de l'API non reconnu.");
        }
    }
}