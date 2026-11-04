const ngrok = require('@ngrok/ngrok');
const fs = require('fs');
const path = require('path');

async function start() {
    console.log('Starting official Ngrok persistent tunnel for unholy-boondocks-snazzy.ngrok-free.dev...');
    
    while (true) {
        try {
            const listener = await ngrok.forward({
                addr: 5000,
                authtoken: '3LVIfjFlfteXGJRWgP4BJGuqpCN_uYRfgK6bBWjvNHSwETBU',
                domain: 'unholy-boondocks-snazzy.ngrok-free.dev'
            });
            const url = listener.url();
            console.log(`\n======================================================`);
            console.log(`NGROK_ACTIVE_URL: ${url}`);
            console.log(`======================================================\n`);
            
            fs.writeFileSync(path.join(__dirname, 'online_url.txt'), url, 'utf-8');
            
            const desktopDir = path.join(process.env.USERPROFILE, 'OneDrive', 'Desktop');
            const finalDesktop = fs.existsSync(desktopDir) ? desktopDir : path.join(process.env.USERPROFILE, 'Desktop');
            
            try {
                fs.writeFileSync(path.join(finalDesktop, 'ONLINE_MOBILE_LINK.url'), `[InternetShortcut]\nURL=${url}\nIconIndex=0\n`);
                fs.writeFileSync(path.join(finalDesktop, 'ONLINE_MOBILE_LINK.txt'), `SK GOLD TERMINAL PERMANENT ONLINE LINK:\n${url}\n\nIs permanent link ko apne mobile phone mein open karein (4G/5G/Wi-Fi kahin bhi 24/7).`);
            } catch (e) {
                console.log('Desktop file write error:', e.message);
            }

            // Keep process active and healthy indefinitely
            await new Promise((resolve) => {
                // Heartbeat every 30 seconds to keep connection alive
                const interval = setInterval(() => {}, 30000);
            });
        } catch (err) {
            console.error('Ngrok Tunnel Error:', err.message || err);
            console.log('Retrying in 5 seconds...');
            await new Promise(r => setTimeout(r, 5000));
        }
    }
}

start();
