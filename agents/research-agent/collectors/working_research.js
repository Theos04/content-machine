const puppeteer = require('puppeteer-termux');

async function researchTopic(topic, depth = 'comprehensive') {
    console.log(`\n🔍 Researching: ${topic}`);
    console.log(`📊 Depth: ${depth}\n`);
    
    let browser = null;
    
    try {
        // For Termux, just connect to existing Chrome CDP
        console.log('📡 Connecting to Chrome CDP at http://127.0.0.1:9222...');
        
        // Connect to the already running Chrome instance
        browser = await puppeteer.connect({
            browserURL: 'http://127.0.0.1:9222',
            defaultViewport: null
        });
        
        console.log('✅ Connected to Chrome CDP');
        
        // Get the first page
        const pages = await browser.pages();
        let page = pages[0];
        
        if (!page) {
            console.log('📄 Creating new page...');
            page = await browser.newPage();
        }
        
        console.log('🌐 Navigating to Google...');
        await page.goto('https://www.google.com', { 
            waitUntil: 'networkidle2', 
            timeout: 30000 
        });
        
        // Handle cookie consent
        try {
            const acceptButton = await page.$('button:has-text("Accept all")');
            if (acceptButton) {
                await acceptButton.click();
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        } catch(e) { 
            console.log('No cookie consent needed');
        }
        
        // Type search query
        console.log(`🔎 Searching for: ${topic}`);
        const searchBox = await page.$('textarea[name="q"]');
        if (!searchBox) {
            throw new Error('Could not find search box');
        }
        
        await searchBox.click();
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
        
        // Try to get "People also ask" if comprehensive
        if (depth === 'comprehensive' && results.length > 0) {
            console.log('\n💡 Tip: Try searching for related terms:');
            const relatedTerms = results.slice(0, 3).map(r => r.title.split(' ').slice(0, 3).join(' '));
            relatedTerms.forEach((term, i) => {
                if (term && !term.includes(topic))
                    console.log(`   • ${term}`);
            });
        }
        
        console.log('\n✅ Research completed successfully!');
        console.log('💡 Chrome CDP remains running for future queries');
        
        // Keep the script running for a moment to see results
        await new Promise(resolve => setTimeout(resolve, 2000));
        
    } catch (error) {
        console.error('❌ Error:', error.message);
        console.error('\n💡 Make sure Chrome CDP is running:');
        console.error('   cd /data/data/com.termux/files/home/storage/downloads/content-machine/agents/research-agent/collectors/chromium_cdp');
        console.error('   bash start_chrome_with_cdp.sh\n');
    }
}

// Get command line arguments
const topic = process.argv[2];
const depth = process.argv[3] || 'comprehensive';

if (!topic) {
    console.log('Usage: node working_research.js "your search topic" [basic|comprehensive]');
    console.log('Example: node working_research.js "waqf board" comprehensive');
    process.exit(1);
}

researchTopic(topic, depth);
