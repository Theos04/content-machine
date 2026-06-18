const puppeteer = require('puppeteer-termux');

async function researchTopic(topic, depth = 'comprehensive') {
    console.log(`\n🔍 Researching: ${topic}`);
    console.log(`📊 Depth: ${depth}\n`);
    
    let browser = null;
    let isOwnBrowser = false;
    
    try {
        // Try to connect to existing Chrome CDP first
        try {
            browser = await puppeteer.connect({
                browserURL: 'http://127.0.0.1:9222',
                defaultViewport: null
            });
            console.log('✅ Connected to existing Chrome CDP instance');
            isOwnBrowser = false;
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
            isOwnBrowser = true;
        }
        
        // Get existing pages or create new one
        let page;
        if (browser.pages) {
            // For launched browser
            const pages = await browser.pages();
            page = pages[0] || await browser.newPage();
        } else if (browser.defaultBrowserContext) {
            // For connected browser via CDP
            const pages = await browser.pages();
            page = pages[0];
            if (!page) {
                page = await browser.newPage();
            }
        } else {
            // Fallback for CDP connection
            page = await browser.newPage();
        }
        
        // Set user agent
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
        
        // Go to Google
        console.log('🌐 Opening Google...');
        await page.goto('https://www.google.com', { waitUntil: 'networkidle2', timeout: 30000 });
        
        // Handle cookie consent
        try {
            const acceptButton = await page.$('button:has-text("Accept all")');
            if (acceptButton) {
                await acceptButton.click();
                await page.waitForTimeout(1000);
            }
        } catch(e) { }
        
        // Type search query
        console.log(`🔎 Searching for: ${topic}`);
        const searchBox = await page.$('textarea[name="q"]');
        if (!searchBox) {
            throw new Error('Could not find search box');
        }
        await searchBox.type(topic);
        await page.keyboard.press('Enter');
        
        // Wait for results
        console.log('⏳ Waiting for search results...');
        await page.waitForSelector('#search', { timeout: 10000 });
        
        // Extract results
        const results = await page.evaluate(() => {
            const items = [];
            const searchResults = document.querySelectorAll('div.g');
            
            searchResults.forEach((result, idx) => {
                const titleElem = result.querySelector('h3');
                const urlElem = result.querySelector('a');
                const snippetElem = result.querySelector('div.VwiC3b');
                
                if (titleElem && urlElem && idx < 15) {
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
                        const heading = q.querySelector('div[role="heading"]');
                        if (heading) questions.push(heading.innerText);
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
        
        // Close only if we launched the browser
        if (isOwnBrowser && browser.close) {
            await browser.close();
        } else {
            console.log('\n💡 Keeping Chrome CDP running for future queries');
            console.log('   To disconnect, press Ctrl+C');
            // Keep the connection alive for a moment
            await page.waitForTimeout(2000);
        }
        
        console.log('\n✅ Research completed successfully!');
        
    } catch (error) {
        console.error('❌ Error:', error.message);
        if (isOwnBrowser && browser && browser.close) {
            await browser.close();
        }
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
