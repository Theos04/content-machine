const puppeteer = require('puppeteer-termux');

(async () => {
    const topic = process.argv[2] || 'waqf board';
    
    console.log(`\n🔍 Searching: ${topic}\n`);
    
    try {
        // Connect to Chrome
        const browser = await puppeteer.connect({
            browserURL: 'http://127.0.0.1:9222'
        });
        
        const pages = await browser.pages();
        const page = pages[0];
        
        // Go to Google search
        await page.goto(`https://www.google.com/search?q=${encodeURIComponent(topic)}`);
        
        // Wait for results
        await page.waitForSelector('#search');
        
        // Get results
        const results = await page.evaluate(() => {
            return Array.from(document.querySelectorAll('div.g')).slice(0, 10).map(r => ({
                title: r.querySelector('h3')?.innerText || '',
                url: r.querySelector('a')?.href || ''
            }));
        });
        
        // Display
        results.forEach((r, i) => {
            console.log(`${i+1}. ${r.title}`);
            console.log(`   ${r.url}\n`);
        });
        
        console.log(`✅ Found ${results.length} results`);
        
    } catch (err) {
        console.error('❌ Error:', err.message);
        console.log('\n📌 Please start Chrome CDP first:');
        console.log('   cd chromium_cdp && bash start_chrome_with_cdp.sh');
    }
    
    process.exit(0);
})();
