const puppeteer = require('puppeteer-termux');

async function researchTopic(topic, depth = 'comprehensive') {
    console.log(`\n🔍 Researching: ${topic}`);
    console.log(`📊 Depth: ${depth}\n`);
    
    let browser;
    try {
        // Try to connect to existing Chrome CDP first
        try {
            browser = await puppeteer.connect({
                browserURL: 'http://127.0.0.1:9222',
                defaultViewport: null
            });
            console.log('✅ Connected to existing Chrome CDP instance');
        } catch (err) {
            console.log('⚠️  No existing Chrome found, launching new instance...');
            browser = await puppeteer.launch({
                headless: false,
                executablePath: '/data/data/com.termux/files/usr/bin/chromium-browser',
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            });
        }
        
        const page = await browser.newPage();
        
        // Set user agent
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
        
        // Go to Google
        console.log('🌐 Opening Google...');
        await page.goto('https://www.google.com', { waitUntil: 'networkidle2', timeout: 30000 });
        
        // Handle cookie consent
        try {
            await page.click('button:has-text("Accept all")', { timeout: 3000 });
            await page.waitForTimeout(1000);
        } catch(e) { }
        
        // Type search query
        console.log(`🔎 Searching for: ${topic}`);
        await page.type('textarea[name="q"]', topic);
        await page.keyboard.press('Enter');
        
        // Wait for results
        await page.waitForSelector('#search', { timeout: 10000 });
        
        // Extract results
        const results = await page.evaluate(() => {
            const items = [];
            const searchResults = document.querySelectorAll('div.g');
            
            searchResults.forEach((result, idx) => {
                const titleElem = result.querySelector('h3');
                const urlElem = result.querySelector('a');
                const snippetElem = result.querySelector('div.VwiC3b');
                
                if (titleElem && urlElem && idx < 15) {  // Get top 15 results
                    items.push({
                        title: titleElem.innerText,
                        url: urlElem.href,
                        snippet: snippetElem ? snippetElem.innerText.substring(0, 300) : ''
                    });
                }
            });
            
            return items;
        });
        
        console.log(`\n📊 Found ${results.length} search results:\n`);
        console.log('═'.repeat(80));
        
        results.forEach((result, index) => {
            console.log(`\n${index + 1}. ${result.title}`);
            console.log(`   🔗 ${result.url}`);
            if (result.snippet) {
                console.log(`   📄 ${result.snippet}`);
            }
            console.log('─'.repeat(80));
        });
        
        // Take screenshot
        const screenshotName = `${topic.replace(/[^a-z0-9]/gi, '_')}_results.png`;
        await page.screenshot({ path: screenshotName, fullPage: true });
        console.log(`\n📸 Screenshot saved: ${screenshotName}`);
        
        // If depth is comprehensive, also get "People also ask" questions
        if (depth === 'comprehensive') {
            try {
                const relatedQuestions = await page.evaluate(() => {
                    const questions = [];
                    const qElements = document.querySelectorAll('div.related-question-pair');
                    qElements.forEach(q => {
                        const text = q.querySelector('div[role="heading"]')?.innerText;
                        if (text) questions.push(text);
                    });
                    return questions;
                });
                
                if (relatedQuestions.length > 0) {
                    console.log(`\n❓ Related questions (People also ask):`);
                    relatedQuestions.forEach((q, i) => {
                        console.log(`   ${i+1}. ${q}`);
                    });
                }
            } catch(e) { }
        }
        
        await browser.close();
        console.log('\n✅ Research completed successfully!');
        
    } catch (error) {
        console.error('❌ Error:', error.message);
        if (browser) await browser.close();
    }
}

// Get command line arguments
const topic = process.argv[2];
const depth = process.argv[3] || 'comprehensive';

if (!topic) {
    console.log('Usage: node google_research.js "your search topic" [basic|comprehensive]');
    console.log('Example: node google_research.js "waqf board" comprehensive');
    process.exit(1);
}

researchTopic(topic, depth);
