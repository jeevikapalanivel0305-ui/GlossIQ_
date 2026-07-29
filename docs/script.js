// ============================================
// GlossIQ Playbook — Navigation & Animations
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const menuToggle = document.getElementById('menuToggle');
    const navLinks = document.querySelectorAll('.nav-link');
    const pages = document.querySelectorAll('.page');
    const mainContent = document.getElementById('mainContent');

    // ─── Page Navigation ────────────────────────────────────────────────
    function navigateToPage(pageId) {
        // Hide all pages
        pages.forEach(page => page.classList.remove('active'));

        // Show target page
        const targetPage = document.getElementById(`page-${pageId}`);
        if (targetPage) {
            targetPage.classList.add('active');

            // Trigger scroll animations for newly visible page
            setTimeout(() => triggerScrollAnimations(), 100);
        }

        // Update nav active state
        navLinks.forEach(link => {
            link.classList.toggle('active', link.dataset.page === pageId);
        });

        // Close mobile sidebar
        sidebar.classList.remove('open');

        // Scroll to top of main content
        mainContent.scrollTo({ top: 0, behavior: 'smooth' });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ─── Nav Link Clicks ────────────────────────────────────────────────
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const pageId = link.dataset.page;
            if (pageId) navigateToPage(pageId);
        });
    });

    // ─── In-page Links (buttons etc.) ───────────────────────────────────
    document.querySelectorAll('[data-page]').forEach(el => {
        if (!el.classList.contains('nav-link')) {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                navigateToPage(el.dataset.page);
            });
        }
    });

    // ─── Mobile Menu Toggle ─────────────────────────────────────────────
    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }

    // Close sidebar on outside click (mobile)
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768) {
            if (!sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        }
    });

    // ─── Scroll Animations ──────────────────────────────────────────────
    function triggerScrollAnimations() {
        const elements = document.querySelectorAll('.animate-on-scroll');
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry, index) => {
                if (entry.isIntersecting) {
                    // Stagger the animations
                    setTimeout(() => {
                        entry.target.classList.add('visible');
                    }, index * 100);
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        elements.forEach(el => {
            if (!el.classList.contains('visible')) {
                observer.observe(el);
            }
        });
    }

    // ─── Initial Load ───────────────────────────────────────────────────
    triggerScrollAnimations();

    // ─── Keyboard Navigation ────────────────────────────────────────────
    document.addEventListener('keydown', (e) => {
        // Ctrl+K to focus search (placeholder for future)
        if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
        }

        // Escape to close mobile sidebar
        if (e.key === 'Escape') {
            sidebar.classList.remove('open');
        }
    });

    // ─── Hash-based Navigation ──────────────────────────────────────────
    function handleHash() {
        const hash = window.location.hash.replace('#', '');
        if (hash) {
            const matchingLink = document.querySelector(`.nav-link[data-page="${hash}"]`);
            if (matchingLink) {
                navigateToPage(hash);
            }
        }
    }

    window.addEventListener('hashchange', handleHash);
    handleHash();

    // ─── Smooth Card Hover Effects ──────────────────────────────────────
    const cards = document.querySelectorAll('.stat-card, .feature-card, .diff-card, .connector-card, .message-card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        });
    });
});
