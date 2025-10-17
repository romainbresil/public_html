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
// --- Script pour le Prédiagnostic de l'Élan Naturel (Logique CII v2 - Locale) ---
// ==========================================================================

const diagContainer = document.getElementById('diag-container');

if (diagContainer) {
    // --- DOM Elements ---
    const conversationStep = document.getElementById('conversation-step');
    const chatLog = document.getElementById('chat-log');
    const interactionZone = document.getElementById('interaction-zone');
    const finalResult = document.getElementById('final-result');
    const analysisContent = document.getElementById('analysis-content');
    const ratingZone = document.getElementById('rating-zone');
    const ratingThanks = document.getElementById('rating-thanks');
    const errorMessage = document.getElementById('error-message');

    // --- Base de données des synthèses ---
    const finalAnalyses = {
        'Matériel-Collectif': `Votre élan est de créer l'Abondance et la Stabilité, soutenu par un fort besoin d'Appartenance collective. Au meilleur de vous-même, vous êtes le pilier de l'équipe : un bâtisseur fiable et un administrateur prudent. Votre génie est de créer des systèmes qui sécurisent la collectivité, offrant une base solide (logistique, budget) pour garantir la pérennité du groupe.\n\nVotre angoisse est la Peur de Manquer (la crise principale). Cette angoisse peut être compliquée par la peur que l'Exclusion du groupe ne vous coupe des ressources et du soutien. Le piège est l'excès de contrôle qui vous pousse à privilégier la sécurité à l'opportunité.\n\nVotre évolution vers plus de sérénité passe par l'audace de faire confiance au système. Peut-être pourriez-vous vous demander : qu'est-ce que vous pourriez déléguer ou lâcher, même si c'est imparfait, pour créer de l'espace dans votre esprit ? Quelle décision ou quel changement de cap professionnel avez-vous récemment reporté par besoin de certitude ?`,
        'Matériel-Individuel': `Votre élan est de garantir une Base Solide et Inébranlable, ce qui est soutenu par une quête d'Expérience Marquante et de Singularité. Au meilleur de vous-même, vous êtes le Maître de l'Excellence Concrète : un entrepreneur tenace. Votre génie est d'utiliser les ressources matérielles pour atteindre un niveau de performance et de singularité qui vous distingue, en combinant vision et discipline.\n\nVotre angoisse est la Peur de Manquer (la crise principale). Cette angoisse peut être compliquée par la peur du Vide/Ennui, ce qui génère une tension. Votre prison est le besoin incessant de tout contrôler pour prévenir l'effondrement, vous coupant parfois de l'opportunité.\n\nPour que cette dynamique trouve son plein équilibre, l'objectif est d'accepter consciemment le risque calculé. Peut-être pourriez-vous vous demander : si vous n'aviez plus rien à prouver, quel projet risqué mais passionnant oseriez-vous vraiment lancer ? Quelle décision ou quel changement de cap professionnel avez-vous récemment reporté par besoin de certitude ?`,
        'Collectif-Matériel': `Votre élan est de Participer et de Contribuer à l'Harmonie collective, soutenu par un besoin d'Ordre et de Sérénité. Au meilleur de vous-même, vous êtes le Ciment Relationnel : un médiateur et un bâtisseur de cohésion. Votre génie est de créer un environnement où chacun se sent à sa juste place en établissant des processus fonctionnels qui garantissent la tranquillité du groupe.\n\nVotre angoisse est la Peur de l'Exclusion (la crise principale). Cette angoisse est compliquée par la peur que le Manque de ressources stables ne rende votre contribution impossible. Votre prison est de vous sacrifier pour vous rendre indispensable, en confondant votre valeur personnelle avec votre utilité pour les autres.\n\nPour que votre dynamique évolue, vous devez oser l'affirmation de soi et la confrontation bienveillante. Peut-être pourriez-vous vous demander : quelle vérité difficile auriez-vous besoin de dire à un collègue ou supérieur pour protéger votre propre équilibre ? Quel rôle avez-vous récemment pris par pure obligation et qui menace votre propre énergie ?`,
        'Collectif-Individuel': `Votre élan est de Faire partie et de Révéler la Valeur du Groupe, soutenu par une quête d'Expérience Humaine Profonde et d'Impact. Au meilleur de vous-même, vous êtes l'Aiguilleur Authentique : un analyste des systèmes humains et un révélateur de potentiel. Votre génie est d'utiliser votre quête d'authenticité pour identifier la juste place de chacun et fédérer les énergies autour d'un but commun.\n\nVotre angoisse est la Peur de l'Exclusion/du Rejet (la crise principale). Cette angoisse peut être compliquée par la peur de Perdre la Connexion intense ou de l'Ennui. Votre risque est de vous focaliser sur l'image du succès pour garantir votre place, en rendant votre quête d'approbation sociale effrénée.\n\nPour que votre dynamique évolue, vous devez vous recentrer sur votre vérité intérieure. Peut-être pourriez-vous vous demander : quelle peur du jugement vous empêche de prendre une position tranchée sur un sujet important ? Quelle personne ou quel collectif cherchez-vous le plus à impressionner en ce moment ?`,
        'Individuel-Matériel': `Votre élan est de Vous Déployer pleinement à travers l'Expérience et la Passion, qui est intimement lié à la Sérénité concrète et à l'abondance des ressources de votre environnement. Au meilleur de vous-même, vous êtes le Stratège Passionné : un initiateur sélectif. Votre génie est de vous engager avec une intensité totale envers les sujets qui vous passionnent, en vous assurant que la base logistique soit stable pour soutenir cet engagement.\n\nVotre angoisse est la Peur de Perdre la Connexion/l'Ennui (la crise principale). Cette angoisse peut être compliquée par la peur que les ressources qui soutiennent votre passion ne manquent. Votre piège est de sauter constamment entre des engagements ou de vous attacher de manière exclusive à un seul sujet.\n\nPour que cette dynamique trouve son plein équilibre, l'objectif est d'apprendre à rester dans la durée. Peut-être pourriez-vous vous demander : Récemment, avez-vous ralenti ou abandonné un projet passionnant simplement parce que le frisson de la nouveauté était retombé ? Jusqu'où êtes-vous prêt(e) à vous sur-adapter ou à simplifier une idée complexe pour être sûr(e) que votre interlocuteur reste engagé(e) et admiratif de votre passion ?`,
        'Individuel-Collectif': `Votre élan est de Vivre des Expériences de Fusion et de Déployer votre Singularité, enrichi par un besoin d'Appartenance et de Reconnaissance. Au meilleur de vous-même, vous êtes le Catalyseur Social : un communicant passionné. Votre génie est d'utiliser votre intensité et votre unicité pour attirer les autres et créer un lien social puissant, amplifiant votre message grâce au groupe.\n\nVotre angoisse est la Peur de l'Ennui/du Vide (la crise principale). Cette angoisse peut être compliquée par la peur de l'Exclusion/du Jugement. Votre risque est de développer un syndrome de l'imposteur si votre identité est trop dépendante de l'admiration externe.\n\nLe travail vers l'autonomie émotionnelle passe par l'affirmation de votre valeur intrinsèque. Peut-être pourriez-vous vous demander : quelle est la chose la plus authentique (et non populaire) que vous aimeriez partager à votre équipe ou à votre public ? Quel projet pourriez-vous réaliser en solo, sans aucune validation ou applaudissement, simplement pour la joie de l'expérience ?`
    };

    // --- Questions & State ---
    const questions = [
        {
            text: "Au lancement d'un nouveau projet ou d'une nouvelle mission, quelle est la première source d'énergie et de satisfaction que vous recherchez ?",
            options: {
                A: { text: "L'assurance de disposer des ressources claires et d'un système bien établi pour garantir la réussite et la sécurité de l'ensemble.", type: 'Matériel' },
                B: { text: "Sentir que votre rôle et votre contribution sont indispensables à l'équilibre et au succès du collectif.", type: 'Collectif' },
                C: { text: "L'excitation de créer quelque chose de singulier et d'atteindre un niveau de performance où vous pouvez vous concentrer intensément.", type: 'Individuel' }
            }
        },
        {
            text: "Si vous êtes confronté(e) à une situation de stress ou d'incertitude importante, quelle est votre première réaction pour retrouver un équilibre intérieur ?",
            options: {
                A: { text: "Me plonger dans une activité passionnante qui me permet d'oublier tout le reste et de me sentir exister intensément.", type: 'Individuel' },
                B: { text: "Reprendre le contrôle en élaborant un plan de secours clair et en vérifiant mes réserves de ressources (temps, argent, énergie).", type: 'Matériel' },
                C: { text: "Chercher la validation ou le soutien sans faille d'un groupe ou de personnes proches pour m'assurer que je suis à ma place.", type: 'Collectif' }
            }
        },
        {
            text: "Quelle est la peur la plus forte qui vous pousse à éviter ou à gérer un conflit ou un désaccord ?",
            options: {
                A: { text: "La crainte de déplaire, de perdre le lien avec l'autre ou que l'intensité de la situation me coupe de l'expérience vécue.", type: 'Individuel' },
                B: { text: "L'impact concret sur l'équilibre financier, la santé ou les conséquences matérielles que cela pourrait engendrer.", type: 'Matériel' },
                C: { text: "La peur viscérale que le conflit ne détruise la cohésion ou que l'on me juge et me mette à l'écart du groupe.", type: 'Collectif' }
            }
        },
        {
            text: "Qu'est-ce qui vous donne la motivation la plus profonde pour vous engager dans une tâche ou un défi ?",
            options: {
                A: { text: "La conviction que mon rôle est essentiel pour la reconnaissance ou l'équilibre d'un groupe ou d'une communauté qui compte pour moi.", type: 'Collectif' },
                B: { text: "La possibilité de vivre une aventure intense, d'endosser un rôle unique et de me sentir transformé(e) par l'action.", type: 'Individuel' },
                C: { text: "La certitude que l'action va solidifier ma base de ressources, améliorer ma stabilité ou assurer ma tranquillité.", type: 'Matériel' }
            }
        },
        {
            text: "Si vous deviez choisir une seule définition du \"succès\" et du \"bien-être\", laquelle serait la plus juste pour vous ?",
            options: {
                A: { text: "Le sentiment de sécurité, la tranquillité d'esprit et un cadre de vie où rien ne manque et tout est sous contrôle.", type: 'Matériel' },
                B: { text: "La liberté de m'exprimer pleinement, d'explorer mes passions et d'avoir un impact qui transforme ma réalité.", type: 'Individuel' },
                C: { text: "Être entouré(e), reconnu(e) à ma juste valeur et avoir une place respectée au sein d'un collectif stable et bienveillant.", type: 'Collectif' }
            }
        }
    ];

    let currentQuestionIndex = 0;
    let userAnswers = [];

    // --- Core Functions ---

    function startConversation() {
        addMessageToLog("Bonjour ! Je vous propose un court échange en 5 questions pour explorer vos moteurs et vos préférences.", 'ai');
        setTimeout(askNextQuestion, 1000);
    }

    function askNextQuestion() {
        if (currentQuestionIndex < questions.length) {
            const questionData = questions[currentQuestionIndex];
            addMessageToLog(questionData.text, 'ai', true);
            showQuestionUI(questionData);
        } else {
            calculateAndShowFinalAnalysis();
        }
    }

    function handleUserAnswer(sequence) {
        if (!/^[ABC]{3}$/i.test(sequence) || new Set(sequence.toUpperCase().split('')).size !== 3) {
            alert("Veuillez entrer une séquence valide de 3 lettres uniques (A, B, C), par exemple : CAB.");
            return;
        }
        
        addMessageToLog(sequence.toUpperCase(), 'user');
        userAnswers.push(sequence.toUpperCase());
        currentQuestionIndex++;
        
        interactionZone.innerHTML = '';
        showSpinner("Analyse de votre réponse...");
        
        setTimeout(askNextQuestion, 1200);
    }
    
    function calculateAndShowFinalAnalysis() {
        showSpinner("Préparation de votre prédiagnostic personnalisé...");

        const scores = {
            'Matériel': 0,
            'Collectif': 0,
            'Individuel': 0
        };
        
        const points = [3, 2, 1];

        userAnswers.forEach((answer, index) => {
            const questionOptions = questions[index].options;
            const chosenOrder = answer.split('');

            chosenOrder.forEach((letter, rank) => {
                const optionType = questionOptions[letter].type;
                scores[optionType] += points[rank];
            });
        });

        const sortedScores = Object.entries(scores).sort(([,a],[,b]) => b-a);
        const cii1 = sortedScores[0][0];
        const cii2 = sortedScores[1][0];

        const analysisKey = `${cii1}-${cii2}`;
        const analysisText = finalAnalyses[analysisKey] || "Une erreur est survenue lors de la génération de votre analyse.";

        setTimeout(() => displayFinalResult(analysisText), 1500);
    }
    
    // --- UI Functions ---

    function addMessageToLog(message, role, isQuestionWithOptions = false) {
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'ai-bubble'}`;
        
        if (isQuestionWithOptions) {
            const questionData = questions[currentQuestionIndex];
            let html = `<p class="font-bold mb-4">${message}</p><ul class="space-y-2 text-sm">`;
            for (const key in questionData.options) {
                html += `<li><span class="font-bold text-gray-700">${key}.</span> ${questionData.options[key].text}</li>`;
            }
            html += `</ul>`;
            bubble.innerHTML = html;
        } else {
            bubble.textContent = message;
        }

        chatLog.appendChild(bubble);
        chatLog.scrollTop = chatLog.scrollHeight;
    }
    
    function showQuestionUI() {
        interactionZone.innerHTML = `
            <div class="mt-4 p-4 bg-gray-100 rounded-lg">
                <label for="user-answer" class="block text-sm font-medium text-gray-700 mb-2">Veuillez classer les 3 options de la plus prioritaire à la moins prioritaire. Répondez uniquement par la séquence des lettres (ex : CAB).</label>
                <div class="flex items-center space-x-3">
                    <input type="text" id="user-answer" maxlength="3" class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-bleu-turquoise focus:border-bleu-turquoise uppercase" placeholder="ex: CAB">
                    <button id="submit-answer-btn" class="brand-secondary-bg text-white font-bold py-2 px-6 rounded-lg hover:bg-opacity-90">Valider</button>
                </div>
            </div>`;

        const submitBtn = document.getElementById('submit-answer-btn');
        const answerInput = document.getElementById('user-answer');
        
        submitBtn.addEventListener('click', () => handleUserAnswer(answerInput.value));
        answerInput.addEventListener('keyup', (event) => {
            if (event.key === 'Enter') {
                handleUserAnswer(answerInput.value);
            }
        });
        answerInput.focus();
    }

    function showSpinner(text = "Analyse en cours...") {
        interactionZone.innerHTML = `<div class="flex justify-center items-center py-4"><div class="spinner"></div><p class="ml-4 text-gray-500 italic">${text}</p></div>`;
    }

    function displayFinalResult(analysisText) {
        conversationStep.classList.add('hidden');
        analysisContent.innerHTML = analysisText.replace(/\n/g, '<br><br>');
        finalResult.classList.remove('hidden');
    }

    function handleError(error) {
        console.error("Erreur:", error);
        conversationStep.classList.add('hidden');
        finalResult.classList.add('hidden');
        errorMessage.classList.remove('hidden');
    }

    // --- Event Listeners ---
    document.querySelectorAll('.rating-btn').forEach(button => {
        button.addEventListener('click', () => {
            ratingZone.classList.add('hidden');
            ratingThanks.classList.remove('hidden');
            console.log(`Note de l'utilisateur : ${button.textContent}`);
        });
    });

    // --- Start ---
    startConversation();
}