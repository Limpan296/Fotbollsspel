# Fotbollsspelen

Två fotbollsspel på en startsida. **Femmanalaget:** bygg ett lag med fem spelare, en storklubb per fråga. **Tre klubbar:** tre klubbar visas, skriv en spelare och få ett poäng för varje klubb han har spelat i. Du får ett poäng per klubb. 30 sekunder per fråga, 1–8 spelare på samma enhet.

Det är en helt statisk sida: inga servrar, inga konton och inga nycklar behövs.

## Filer

| Fil | Vad |
|---|---|
| `index.html` | Hela sidan: startsida, Femmanalaget, Tre klubbar och Vem är jag? |
| `config.js` | Inställningar för onlineläget (Supabase-adress och nyckel) |
| `vemarjag.json` | Ledtrådar till Vem är jag? (900 frågor, byggda ur samma data) |
| `players.json` | Spelardata (5,4 MB), byggd från github.com/salimt/football-datasets |
| `uppdatera-data/build_players_data.py` | Skriptet som bygger om `players.json` med färsk data |

Filerna `index.html`, `config.js`, `players.json` och `vemarjag.json` måste ligga i samma mapp.

## Köra lokalt

Öppna inte `index.html` direkt med dubbelklick. Webbläsaren blockerar då inläsningen av `players.json`. Starta en liten server i mappen:

    python3 -m http.server 8000

och öppna http://localhost:8000

## Publicera (gratis, välj ett)

**Netlify Drop** (enklast, tar en minut): gå till https://app.netlify.com/drop och dra hela mappen `fotbollsspelen` till rutan. Du får en riktig länk direkt. Skapa gratis konto om du vill behålla den.

**GitHub Pages:** skapa ett repo, ladda upp `index.html` och `players.json`, gå till Settings > Pages och välj branchen `main` och mappen `/ (root)`. Länken blir `https://DITTNAMN.github.io/REPONAMN/`.

**Cloudflare Pages / Vercel:** koppla ett repo med filerna ovan. Ingen byggkommando behövs, publicera mappen som den är.

## Spela online (valfritt, gratis)

Onlineläget låter 2–8 personer spela på varsin enhet. En skapar match och får en kod på 5 tecken, de andra skriver in koden (eller öppnar länken). Alla får samma fråga samtidigt och efter varje fråga syns allas svar. Spelen på en enhet fungerar som förut. Onlineläget behöver ett eget gratis Supabase-projekt som bara förmedlar meddelanden mellan spelarna. Inga tabeller och ingen SQL behövs.

1. Skapa ett konto på https://supabase.com och välj New project (valfritt namn och lösenord, välj en region nära er).
2. Gå till Project Settings > API. Kopiera **Project URL** och nyckeln **anon public**.
3. Öppna `config.js` och klistra in dem:

       window.FS_CONFIG = {
         supabaseUrl: "https://abcdxyz.supabase.co",
         supabaseKey: "eyJ..."
       };

4. Publicera om mappen. På startsidan visas nu knapparna "Femmanalaget online" och "Tre klubbar online".

**Vem är jag?** spelas bara online (2–8 spelare). Alla ser samma ledtråd, en ny kommer var 20:e sekund, och rätt svar ger 10, 8, 6, 4 eller 2 poäng beroende på ledtråd. Man kan svara en gång per ledtråd. Värden bedömer svaren, så ett fel svar syns bara för den som gissade.

Bra att veta:
- Anon-nyckeln är gjord för att ligga i webbsidor. Använd aldrig `service_role`-nyckeln.
- Matchen bor i värdens webbläsare. Stänger värden fliken eller tappar nätet avslutas matchen för alla. En spelare som tappar anslutningen får noll poäng på frågan.
- Gratisprojekt i Supabase pausas efter ca en veckas inaktivitet. Logga in och klicka Restore om onlineläget slutar svara.
- Onlineläget kräver att sidan är publicerad på egen adress. Det fungerar inte i Claude-artefakten.

## Uppdatera spelardatan

    python3 uppdatera-data/build_players_data.py .

Skriptet hämtar de CSV-filer som behövs från GitHub, räknar unika seniorklubbar per spelare och skriver en ny `players.json` i mappen. Kör sedan `python3 uppdatera-data/build_vemarjag.py players.json .` för att bygga om ledtrådarna (`vemarjag.json`). Ladda sedan upp de nya filerna. Hela körningen tar några minuter (transferfilen är ca 80 MB). Bara Python 3 behövs, inga extra paket.

## Datakälla och villkor

Spelardatan kommer från https://github.com/salimt/football-datasets, som i sin tur bygger på Transfermarkt. Repot har ingen licensfil. Det är fint att dela med kollegor, men kolla villkoren innan du publicerar det brett eller tjänar pengar på det.

## Ledtrådarna i Vem är jag?

Alla uppgifter kommer ur datasetet: födelseland eller medborgarskap, antal unika seniorklubbar, position, fot, klubbar, klubbarnas länder, nuvarande eller senaste klubb, landskamper och födelseår. Titlar och utmärkelser finns inte i datasetet och används därför inte. Varje fråga kontrolleras mot hela datasetet så att bara en spelare passar på alla ledtrådar. Klubbland saknas för en del små klubbar, och då nämns bara de länder som är kända. Landskamper är avrundade nedåt, till exempel "minst 80".

## Så räknas poängen

- Unika klubbar per spelare, efter klubb-ID, så återvändande till en klubb räknas en gång.
- Lån räknas. Ungdoms-, B-/reserv- och "klubbar" som Retired och Without Club räknas inte.
- Datasetet har mest spelare från senare år, så äldre legender saknas.
