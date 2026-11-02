#!/usr/bin/env node
// Generate the notification signing key pair once. Store VAPID_PRIVATE_KEY only
// as a Cloudflare Pages *Secret*; the public key may be a plain variable.
const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
const jwk = await crypto.subtle.exportKey('jwk', pair.privateKey);
const pub = Buffer.from(await crypto.subtle.exportKey('raw', pair.publicKey)).toString('base64url');
console.log('VAPID_PUBLIC_KEY=' + pub);
console.log('VAPID_PRIVATE_KEY=' + jwk.d);
console.log('\nSave the private key in a password manager and as a Cloudflare Secret. Never commit it, paste it in chat or put it in site files.');
