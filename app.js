// App state and navigation
let currentScreen = 'screen-splash';
let currentTab = 'screen-dashboard';

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    // Splash screen animation
    simulateSplash();
    
    // Prevent forms from submitting and handle API
    document.getElementById('login-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = e.target.querySelector('input[type="email"]').value;
        const password = e.target.querySelector('input[type="password"]').value;
        const btn = e.target.querySelector('button');
        
        const origText = btn.innerText;
        btn.innerText = 'Signing In...';
        btn.disabled = true;
        
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, name: ""})
            });
            const data = await res.json();
            if (res.ok) {
                localStorage.setItem('user_id',    data.user_id);
                localStorage.setItem('user_name',  data.name);
                localStorage.setItem('user_email', email);
                navigateTo('main-app');
            } else {
                alert(data.detail || "Login failed");
            }
        } catch (err) {
            console.error(err);
            alert("Backend offline. Bypassing for preview...");
            navigateTo('main-app');
        }
        btn.innerText = origText;
        btn.disabled = false;
    });
    
    document.getElementById('signup-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const inputs = e.target.querySelectorAll('input');
        const name = inputs[0].value.trim();
        const email = inputs[1].value.trim();
        const password = inputs[2].value;
        const btn = e.target.querySelector('button');

        if (!name || !email || !password) return;

        btn.innerHTML = '<i class="ph ph-circle-notch" style="animation:spin 0.8s linear infinite"></i> Creating Account...';
        btn.disabled = true;

        // Optimistic: store tentative data immediately and navigate right away
        const tempId = 'User_' + Date.now();
        localStorage.setItem('user_id',    tempId);
        localStorage.setItem('user_email', email);
        localStorage.setItem('user_name',  name);
        navigateTo('screen-onboarding');

        // Save to backend in background (non-blocking)
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
            const res = await fetch('/api/signup', {
                method:  'POST',
                headers: {'Content-Type': 'application/json'},
                body:    JSON.stringify({email, password, name}),
                signal:  controller.signal
            });
            clearTimeout(timeout);
            const data = await res.json();
            if (res.ok) {
                // Update with real server ID
                localStorage.setItem('user_id', data.user_id);
                localStorage.setItem('user_name', data.name);
            }
        } catch (err) {
            clearTimeout(timeout);
            console.warn('Signup background save failed (offline mode):', err.message);
        }

        btn.innerText = 'Join the Network';
        btn.disabled = false;
    });

    // Handle Onboarding form
    document.getElementById('onboarding-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const reviewer_type = document.getElementById('q1-type').value;
        const strictness = document.getElementById('q2-strictness').value;
        const dealbreaker = document.getElementById('q3-dealbreaker').value;
        const shopping_category = document.getElementById('q4-category').value;
        const explanation_length = document.getElementById('q5-length').value;
        const email = localStorage.getItem('user_email') || "preview@domain.com";
        const btn = e.target.querySelector('button');
        
        btn.innerText = 'Saving...';
        btn.disabled = true;
        
        try {
            await fetch('/api/save_preferences', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, reviewer_type, strictness, dealbreaker, shopping_category, explanation_length})
            });
            navigateTo('main-app');
        } catch (err) {
            navigateTo('main-app');
        }
    });

    // Handle Profile Picture Upload
    document.getElementById('profile-pic-upload')?.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(evt) {
            const dataUrl = evt.target.result;
            localStorage.setItem('profile_pic', dataUrl);
            updateUIWithUser(); // Refresh the UI to show the image
        };
        reader.readAsDataURL(file);
    });
});

function simulateSplash() {
    let progress = 0;
    const progressFill = document.getElementById('splash-progress');
    const progressText = document.getElementById('splash-progress-text');
    
    const interval = setInterval(() => {
        progress += Math.floor(Math.random() * 15) + 5;
        if (progress > 100) progress = 100;
        
        progressFill.style.width = `${progress}%`;
        progressText.innerText = `${progress}%`;
        
        if (progress === 100) {
            clearInterval(interval);
            setTimeout(() => {
                // Respect ?start= param from landing page CTAs
                const params = new URLSearchParams(window.location.search);
                const start  = params.get('start');
                if (start === 'signup') {
                    navigateTo('screen-signup');
                } else {
                    navigateTo('screen-login');
                }
            }, 500);
        }
    }, 300);
}

function navigateTo(screenId) {
    // Hide all main screens
    document.querySelectorAll('.screen').forEach(el => {
        el.classList.remove('active');
    });
    
    // Show target screen
    document.getElementById(screenId).classList.add('active');
    currentScreen = screenId;
    
    // If navigating to main-app, ensure dashboard is shown and UI is populated
    if (screenId === 'main-app') {
        updateUIWithUser();
        navigateToTab('screen-dashboard');
    }
}

function updateUIWithUser() {
    const name = localStorage.getItem('user_name') || "Agent";
    
    // Update Dashboard Welcome
    const welcomeTitle = document.getElementById('welcome-title');
    if (welcomeTitle) welcomeTitle.innerText = `Welcome, ${name}`;
    
    // Update Profile Screen
    const modelUsername = document.getElementById('model-username');
    if (modelUsername) modelUsername.innerText = `${name}'s Profile`;
    
    const modelAvatar = document.getElementById('model-avatar');
    const initialSpan = document.getElementById('model-avatar-initial');
    const savedPic = localStorage.getItem('profile_pic');
    
    if (savedPic && modelAvatar) {
        // If they have a profile pic, hide initial and set background
        if(initialSpan) initialSpan.style.display = 'none';
        modelAvatar.style.backgroundImage = `url(${savedPic})`;
        modelAvatar.style.backgroundSize = 'cover';
        modelAvatar.style.backgroundPosition = 'center';
    } else if (initialSpan) {
        initialSpan.innerText = name.charAt(0).toUpperCase();
    }
    
    // Update Chat Welcome
    const welcomeMsg = document.getElementById('chat-welcome-msg');
    if (welcomeMsg) {
        welcomeMsg.innerText = `Hi ${name}! I'm your personalized recommendation agent. I've loaded your modeled profile. What are you looking for today? (Try asking for movies, food, drinks, or any product.)`;
    }
}

function navigateToTab(tabId) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(el => {
        el.classList.remove('active');
    });
    
    // Show target tab
    document.getElementById(tabId).classList.add('active');
    currentTab = tabId;
    
    // Update bottom nav state if applicable
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('active');
    });
    
    // Map tabs to nav items
    const navMap = {
        'screen-dashboard': 'nav-dashboard',
        'screen-user-model': 'nav-user-model',
        'screen-simulate': 'nav-simulate',
        'screen-recommend': 'nav-recommend',
        'screen-evaluate': 'nav-evaluate'
    };
    
    const activeNav = navMap[tabId];
    if (activeNav) {
        document.getElementById(activeNav)?.classList.add('active');
    }
}

// User Modeling Action
async function runExtraction() {
    const btn = document.querySelector('#screen-user-model .btn-outline-small');
    const originalText = btn.innerText;
    btn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Extracting...';
    btn.disabled = true;

    try {
        const userId = localStorage.getItem('user_id') || 'User_014';
        const response = await fetch('/api/extract_signals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });
        const data = await response.json();
        console.log("Extraction Data:", data);

        // ── Update signals grid ──────────────────────────────────────────────
        const grid = document.querySelector('.signals-grid');
        if (grid && data.signals && data.signals.length > 0) {
            const allSignals = [...(data.signals || []), ...(data.biases || [])];
            grid.innerHTML = allSignals.map(s =>
                `<div class="signal-tag">${s}</div>`
            ).join('');
        }

        // ── Update avg rating in profile header ──────────────────────────────
        if (data.avg_rating != null) {
            const profileInfo = document.querySelector('#screen-user-model .profile-info p');
            if (profileInfo) {
                profileInfo.innerHTML = `Avg Rating: <strong>${data.avg_rating} / 5.0</strong>` +
                    (data.tone ? ` &bull; Tone: <em>${data.tone}</em>` : '');
            }
        }

        btn.innerText = '✓ Signals Updated';
        btn.style.backgroundColor = 'var(--success)';
        btn.style.color = 'white';
        btn.style.borderColor = 'var(--success)';
    } catch (err) {
        console.error("Backend Error:", err);
        btn.innerText = 'Backend Not Connected';
        btn.style.borderColor = 'var(--danger)';
        btn.style.color = 'var(--danger)';
    }

    setTimeout(() => {
        btn.innerText = originalText;
        btn.style.backgroundColor = '';
        btn.style.color = '';
        btn.style.borderColor = '';
        btn.disabled = false;
    }, 3000);
}

// ── Task 1: Simulate Review ──────────────────────────────────────────────────
async function simulateReview() {
    const btn = document.getElementById('simulate-run-btn');
    const originalHTML = btn.innerHTML;
    const resultDiv = document.getElementById('simulation-result');

    // Read inputs
    const itemInput       = (document.getElementById('simulate-item-input')?.value || '').trim();
    const catalogueSelect = document.getElementById('simulate-item-select');
    const itemId          = catalogueSelect ? catalogueSelect.value : 'Item_992';
    const customPersona   = (document.getElementById('simulate-persona-input')?.value || '').trim();
    const userId          = localStorage.getItem('user_id') || 'User_014';

    btn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Simulating…';
    btn.disabled  = true;
    resultDiv.classList.add('hidden');

    try {
        const response = await fetch('/api/simulate', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id:          userId,
                item_id:          itemId,
                item_description: itemInput,   // free-text wins on the backend
                custom_persona:   customPersona
            })
        });
        const data = await response.json();

        // Build star string from float rating
        const rating  = parseFloat(data.rating) || 0;
        const filled  = Math.round(rating);
        const stars   = '★'.repeat(filled) + '☆'.repeat(5 - filled);

        document.querySelector('.prediction-card .rating-stars').innerText =
            `${stars} (${rating.toFixed(1)})`;
        document.querySelector('.simulated-text p').innerText  = `"${data.review}"`;
        document.querySelector('.prediction-card .confidence').innerText =
            `${data.confidence} Confidence`;

        const reasoningList = document.querySelector('.reasoning-list');
        reasoningList.innerHTML = '';
        (data.reasoning || []).forEach(r => {
            const li = document.createElement('li');
            li.innerHTML = r;
            reasoningList.appendChild(li);
        });

        btn.innerHTML = originalHTML;
        btn.disabled  = false;
        resultDiv.classList.remove('hidden');

        // Animate in
        resultDiv.style.opacity   = '0';
        resultDiv.style.transform = 'translateY(12px)';
        setTimeout(() => {
            resultDiv.style.transition = 'all 0.4s ease';
            resultDiv.style.opacity    = '1';
            resultDiv.style.transform  = 'translateY(0)';
        }, 50);

    } catch (err) {
        console.error('Backend Error:', err);
        btn.innerHTML = '<i class="ph ph-warning"></i> Backend offline — showing fallback';
        btn.disabled  = false;

        // Show fallback result so the UI still demonstrates Task 1
        document.querySelector('.prediction-card .rating-stars').innerText = '★★★☆☆ (3.4)';
        document.querySelector('.simulated-text p').innerText =
            '"The features are good but the price tag doesn\'t justify the battery life. Solid build quality though."';
        document.querySelector('.prediction-card .confidence').innerText = '92% Confidence';
        resultDiv.classList.remove('hidden');

        setTimeout(() => { btn.innerHTML = originalHTML; }, 3000);
    }
}

// ── Accordion helper (Task 1 persona panel) ──────────────────────────────────
function toggleAccordion(bodyId, toggleBtn) {
    const body  = document.getElementById(bodyId);
    const arrow = toggleBtn.querySelector('.acc-arrow');
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display  = isOpen ? 'none' : 'block';
    if (arrow) arrow.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
}

// ── Persona panel toggle (Task 2) ─────────────────────────────────────────────
window.toggleRecommendPersona = function() {
    const panel  = document.getElementById('recommend-persona-panel');
    const btn    = document.getElementById('persona-toggle-btn');
    if (!panel) return;
    const isOpen = panel.style.display !== 'none';
    panel.style.display = isOpen ? 'none' : 'block';
    if (btn) btn.style.color = isOpen ? '' : 'var(--primary)';
};

// Evaluation Tab Switch
function switchEvalTab(tabName) {
    document.querySelectorAll('.eval-tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.eval-content').forEach(el => el.classList.remove('active'));
    
    if (tabName === 'taskA') {
        document.querySelector('.eval-tab:nth-child(1)').classList.add('active');
        document.getElementById('eval-taskA').classList.add('active');
    } else {
        document.querySelector('.eval-tab:nth-child(2)').classList.add('active');
        document.getElementById('eval-taskB').classList.add('active');
    }
}

// Chat Functionality
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    
    const chatContainer = document.getElementById('chat-messages');
    
    // Add user message
    const userHTML = `
        <div class="message user">
            <div class="msg-bubble">${msg}</div>
        </div>
    `;
    chatContainer.insertAdjacentHTML('beforeend', userHTML);
    input.value = '';
    
    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    // Simulate agent typing
    const typingHTML = `
        <div class="message system" id="typing-indicator">
            <div class="msg-avatar"><i class="ph-fill ph-robot"></i></div>
            <div class="msg-bubble"><i class="ph ph-dots-three ph-fill" style="animation: pulse 1s infinite"></i></div>
        </div>
    `;
    chatContainer.insertAdjacentHTML('beforeend', typingHTML);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    // ── Task 2: read custom persona if panel is open ──
    const customPersonaRec = (document.getElementById('recommend-persona-input')?.value || '').trim();

    try {
        const response = await fetch('/api/recommend', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id:       localStorage.getItem('user_id') || 'User_014',
                message:       msg,
                custom_persona: customPersonaRec
            })
        });
        const data = await response.json();
        
        // Remove typing indicator
        const typingEl = document.getElementById('typing-indicator');
        if (typingEl) typingEl.remove();
        
        let carouselHTML = '';
        if (data.items && data.items.length > 0) {
            let cards = data.items.map(item => {
                const keyword   = encodeURIComponent(item.image_keyword || item.category || 'product');
                const imgSrc    = `https://source.unsplash.com/80x80/?${keyword}&sig=${Math.floor(Math.random()*9999)}`;
                const catBadge  = item.category  ? `<span class="rec-badge">${item.category}</span>`  : '';
                const priceBadge = item.price_level ? `<span class="rec-badge rec-badge-price">${item.price_level}</span>` : '';
                const qualLine  = item.quality_score ? `<div class="rec-quality">Quality: ${parseFloat(item.quality_score).toFixed(1)}/5</div>` : '';
                return `
                <div class="rec-card">
                    <img src="${imgSrc}" style="width: 56px; height: 56px; border-radius: 8px; object-fit: cover; flex-shrink: 0;" alt="${item.name}" onerror="this.src='https://placehold.co/56x56/1a1a2e/7c3aed?text=📦'">
                    <div class="rec-info">
                        <h5>${item.name}</h5>
                        <div style="display:flex;gap:4px;flex-wrap:wrap;margin:2px 0;">${catBadge}${priceBadge}</div>
                        <div class="rec-score">Match: ${item.score}</div>
                        ${qualLine}
                        <p>${item.reason}</p>
                    </div>
                </div>
            `;
            }).join('');
            carouselHTML = `<div class="rec-carousel">${cards}</div>`;
        }
        
        const agentHTML = `
            <div class="message system">
                <div class="msg-avatar"><i class="ph-fill ph-robot"></i></div>
                <div class="msg-bubble">
                    <p>${data.response_text}</p>
                    ${carouselHTML}
                </div>
            </div>
        `;
        chatContainer.insertAdjacentHTML('beforeend', agentHTML);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        // Speak the agent's response
        speakText(data.response_text);
        
    } catch (err) {
        console.error("Backend Error:", err);
        document.getElementById('typing-indicator').remove();
        chatContainer.insertAdjacentHTML('beforeend', `
            <div class="message system">
                <div class="msg-avatar"><i class="ph-fill ph-robot"></i></div>
                <div class="msg-bubble" style="color: red;">Error: Cannot connect to the Python backend. Make sure it's running.</div>
            </div>
        `);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

// Allow Enter key to send message
document.getElementById('chat-input')?.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Logout function
window.logout = function() {
    if (confirm('Are you sure you want to log out?')) {
        // Clear all stored session data
        ['user_id', 'user_email', 'user_name', 'profile_pic'].forEach(k => localStorage.removeItem(k));
        // Return to landing page
        window.location.href = '/';
    }
};

// Text-to-Speech Engine
let voiceEnabled = true;

window.toggleVoice = function() {
    voiceEnabled = !voiceEnabled;
    const icon = document.getElementById('voice-icon');
    if (voiceEnabled) {
        icon.classList.remove('ph-speaker-slash');
        icon.classList.add('ph-speaker-high');
        speakText("Voice response enabled.");
    } else {
        icon.classList.remove('ph-speaker-high');
        icon.classList.add('ph-speaker-slash');
        window.speechSynthesis.cancel();
    }
};

function speakText(text) {
    if (!voiceEnabled || !window.speechSynthesis) return;
    
    // Stop any current audio
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    
    // Clean up text (remove markdown asterisks or special characters)
    const cleanText = text.replace(/\*/g, '');
    utterance.text = cleanText;
    
    // Optional: try to grab a good default voice
    const voices = window.speechSynthesis.getVoices();
    const agentVoice = voices.find(v => v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('Natural')) || voices[0];
    if (agentVoice) utterance.voice = agentVoice;
    
    utterance.rate = 1.0;
    utterance.pitch = 1.1; // Slightly higher pitch for a friendly agent tone
    
    window.speechSynthesis.speak(utterance);
}

// Speech-to-Text (Microphone Recording)
let recognition;
let isRecording = false;

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    
    recognition.onresult = function(event) {
        let interimTranscript = '';
        let finalTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }
        
        const inputField = document.getElementById('chat-input');
        if (finalTranscript) {
            inputField.value = finalTranscript;
        } else {
            inputField.value = interimTranscript;
        }
    };
    
    recognition.onerror = function(event) {
        console.error("Speech recognition error", event.error);
        stopRecording();
    };
    
    recognition.onend = function() {
        stopRecording();
        // Auto-send the message when the user stops talking
        const inputField = document.getElementById('chat-input');
        if (inputField && inputField.value.trim() !== '') {
            sendMessage();
        }
    };
}

window.toggleRecording = function() {
    if (!recognition) {
        alert("Speech recognition is not supported in your browser (try Chrome/Edge).");
        return;
    }
    
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
};

function startRecording() {
    isRecording = true;
    const micBtn = document.getElementById('mic-btn');
    if(micBtn) micBtn.innerHTML = '<i class="ph-fill ph-stop-circle" style="color: red;"></i>';
    const inputField = document.getElementById('chat-input');
    if(inputField) inputField.placeholder = "Listening...";
    recognition.start();
}

function stopRecording() {
    isRecording = false;
    const micBtn = document.getElementById('mic-btn');
    if(micBtn) micBtn.innerHTML = '<i class="ph-fill ph-microphone"></i>';
    const inputField = document.getElementById('chat-input');
    if(inputField) inputField.placeholder = "Ask for recommendations...";
}
