# KEHA P67 QA — Finnish email drafts sourced from the living evidence ledger

**Status:** First authenticated QA P67 PUBLISHED and ARCHIVED searches succeeded in a short 30-minute window with zero matching records (QA-013). A separate production credential request still awaits adequate **nonempty-data** and remaining validation, or KEHA's written agreement on testing scope.  
**Ground truth:** [KEHA P67 v2 QA test ledger](KEHA_P67_QA_TEST_LEDGER.md). Update the evidence ledger first after every test, then update these drafts.  
**Privacy:** Never copy the QA subscription key into either email. The public repository intentionally does not contain the operator's home public IPv4; insert it only in the private email to KEHA.

## 1. Interim reply: report first successful QA searches and request test-scope guidance

**Suggested subject:** Re: Työmarkkinatorin P67 v2 -hakurajapinta / Komplyint Oy – ensimmäiset onnistuneet QA-haut ja testauksen jatko

Hei,

Kiitos Komplyint Oy:lle 26.10.2026 toimitetusta Työmarkkinatorin työpaikkailmoitusten hakurajapinnan (P67 v2) testiympäristön käyttöoikeudesta.

Olemme jatkaneet SmartPloy-palvelun P67 v2 -rajapinnan testausta. Alkuperäisen testitietokoneen suora verkkoyhteys estyi, mutta erillisen OVH-palvelimen kautta muodostetulla suojatulla SSH/SOCKS-yhteydellä olemme nyt saaneet **onnistuneet tunnistetut PUBLISHED- ja ARCHIVED-hakuvastaukset** KEHA:n QA-rajapinnasta.

**Tähän mennessä tehdyt tarkistukset (28.–29.10.2026): yhteensä 13, joista 9 hyväksyttiin (mukaan lukien yksi uusintatesti ja yksi tunnistettu QA-testausajo) ja 4 estyi alkuperäisen suoran verkkoyhteyden vuoksi. Viimeisin ajo suoritti onnistuneesti kaksi tunnistettua P67 POST -hakua.**
- Testausohjelma käynnistyy oikein, ja QA-tila sekä tilaustunnuksen olemassaolo on vahvistettu paikallisesti. Tämä ei vielä osoita, että palvelin olisi hyväksynyt tunnuksen.
- Todellinen PUBLISHED/ARCHIVED-hakutesti pysähtyy ennen HTTP-vastausta ilmoitukseen `QA_NETWORK_OR_TLS`.
- Suora HTTPS-yhteyskokeilu osoitteeseen `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` päättyy TCP-yhteyden aikakatkaisuun noin 10 sekunnissa (`curl`-virhekoodi 28, HTTP 000). **Uusintatesti 29.10.2026 vahvisti saman tuloksen** (IPv4, `curl_exit=28`, HTTP 000; TCP- ja TLS-yhteyttä ei muodostunut). TLS-kättelyä tai API-tunnistautumista ei päästä aloittamaan.
- Vertailutesti `https://github.com` -palveluun toimii IPv4-yhteydellä (HTTP 200). KEHA:n QA-osoitteeseen yhteys ei toimi testitietokoneelta myöskään pakotetulla IPv4:llä.
- Erilliseltä OVH-palvelimeltamme HTTPS-yhteys QA-palvelimeen toimii: `curl -I` palauttaa HTTP 404 -vastauksen, ja TCP-yhteys (0,104 s) sekä TLS-kättely (0,148 s) onnistuvat. **Avaimeton POST-testi ja sen uusinta palauttivat HTTP 401 -vastauksen** (alkuperäinen TCP 0,021 s / TLS 0,066 s; uusinta TCP 0,022 s / TLS 0,078 s). Tämä osoittaa pyynnön saavuttavan tunnistautumista tai käyttöoikeutta edellyttävän HTTP-tason, **ei** vielä rajapinta-avaimen hyväksyntää tai työpaikkatietojen hakua.
- **Myös Linux Mint -testitietokoneelta** tehdyn SSH/SOCKS-välityksen kautta avaimeton POST-pyyntö onnistui verkkoyhteytenä ja sai HTTP 401 -vastauksen (`TLS=0,352 s`; `curl_exit=0`). Tämä osoittaa, että erillisen OVH-palvelimen kautta voidaan tehdä QA-pyyntöjä siirtämättä tilaustunnusta OVH:n levylle tai tuotantosovellukseen.
- **Testi QA-013 (29.10.2026):** virallinen QA-osoite, tunnistettu PUBLISHED-haku onnistui; tunnistettu ARCHIVED-haku onnistui. Molemmissa käytettiin 30 minuutin muutosajankohtarajausta, ja molemmissa osumia oli **0**. Tulos todentaa tunnistautumisen ja tyhjän hakuvastauksen käsittelyn, **ei** vielä yksittäisten työpaikkatietueiden lukemista tai arkistointiprosessin toimintaa todellisilla tietueilla.
- Rajapinta-avainta ei tallennettu OVH-palvelimen tuotantopalveluihin, eikä testissä tehty tietokantakirjoituksia, välitetty työpaikkatietoja ulkoiseen tekoälyyn tai lähetetty työnhakemuksia.
- Salaisia avaimia, henkilötietoja tai hakutuloksia ei ole toimitettu ulkopuolisiin raportteihin.

**Testitietokoneen julkinen lähtevä IPv4:** [LISÄÄ VAIN KEHALLE LÄHETETTÄVÄÄN YKSITYISEEN VIESTIIN]

**OVH-palvelimen julkinen lähtevä IPv4:** [LISÄÄ VAIN KEHALLE LÄHETETTÄVÄÄN YKSITYISEEN VIESTIIN]

Voisitteko ystävällisesti vahvistaa, riittääkö onnistunut tunnistettu haku ja muut toiminnalliset testit tuotantoon siirtymisen arviointiin vai edellytättekö tiettyjä lisätestejä? Jatkamme nyt laajemmalla muutosajankohtarajauksella, jotta voimme varmentaa myös varsinaisten ilmoitustietueiden käsittelyn. Voimmeko käyttää QA-testaukseen erillistä testiprosessia OVH-palvelimen verkosta, ja tarvitaanko muita IP-avauksia tai käyttöoikeuksia?

Jatkamme seuraavaksi ilmoitusten haku-, suodatus-, kieli-, tietorakenne- ja tietosuojatestejä. Toimitamme päivitetyn yhteenvedon, kun laajemmat testit ja mahdolliset lisätestivaatimukset on käsitelty.

Kiitos avustanne!

Ystävällisin terveisin,

---

## 2. Future reply: request production access ONLY after real QA acceptance

**Do not send until** outstanding scenarios (especially nonempty posting parsing, attribution and archival lifecycle) have real QA evidence or an explicitly agreed scope with KEHA. QA-013 proves P67 authentication and two zero-result searches only; local synthetic CI success does not replace provider evidence.

**Suggested subject:** Työmarkkinatorin P67 v2 -hakurajapinta – QA-testauksen tulokset ja tuotantotunnusten pyyntö / Komplyint Oy

Hei,

Olemme toteuttaneet Työmarkkinatorin P67 v2 -työpaikkailmoitusten hakurajapinnan testiympäristön testauksen Komplyint Oy:n SmartPloy-palvelua varten.

**Testiympäristö:** `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings`  
**Testausjakso:** alkaen 28.10.2026; [LOPULLINEN PÄÄTTYMISPÄIVÄMÄÄRÄ, kun tiedossa]  
**Yhteenveto:** QA-013 (29.10.2026) PUBLISHED- ja ARCHIVED-haut hyväksytty, molemmat 0 osumaa 30 minuutin aikaikkunassa. Muita testejä täydennettävä ennen tätä tuotantotunnuspyyntöä.

| Testi | Toteutunut tulos (täytetään todennetun testin jälkeen) |
| --- | --- |
| P67-01 QA-yhteys ja tunnistautuminen | Hyväksytty QA-013 (29.10.2026), SSH/SOCKS-tunnelin kautta |
| P67-02 Julkaistujen ilmoitusten haku | Onnistui QA-013, 0 osumaa (30 min); ei vielä tietueiden lukutestiä |
| P67-03 Arkistoitujen ilmoitusten haku | Onnistui QA-013, 0 osumaa (30 min); ei vielä arkistoitujen tietueiden käsittelytestiä |
| P67-04 Muutosajankohdan rajaus ja tyhjät tulokset | Osittain: 30 min -ikkuna ja tyhjät vastaukset hyväksytty; 120 min -testi seuraavaksi |
| P67-05 Kieliversioiden käsittely | [TULOS] |
| P67-06 Työpaikkatietojen rakenteen tarkistus | [TULOS] |
| P67-07 Päivitysten, kaksoiskappaleiden ja arkistoinnin käsittely | [TULOS] |
| P67-08 Virhetilanteet, tietosuoja ja käyttöehtojen mukainen käsittely | Osittain: QA-013 ei tuotantokirjoituksia, ulkoista AI-välitystä tai työnhakemuksia; muut testit avoinna |

Ohjelmiston erillisessä synteettisessä testauksessa on myös hyväksytysti suoritettu [PÄIVITÄ AJANTASAINEN TARKKA LUKU] automaattista Python/PostgreSQL-testiä sekä käyttöliittymä- ja integraatiotarkistuksia. Nämä ilmoitetaan erillisenä ohjelmiston laadunvarmistuksena, ei korvaavina rajapinnan QA-testituloksina.

Käytämme haettuja työpaikkailmoituksia vain rajapinnan käyttöehtojen sallimalla tavalla ja noudatamme alkuperäisen lähteen ilmoittamista, arkistoitujen ilmoitusten käsittelyä ja tietojen edelleenluovutusta koskevia rajoituksia.

Voisitteko vahvistaa, ovatko suoritetut testit riittävät tuotantoympäristöön siirtymiselle, ja toimittaa tuotantoympäristön erilliset käyttöoikeudet sekä mahdolliset IP-avausohjeet?

Ystävällisin terveisin,

---

## Evidence and revision procedure

- New operator receipt → append QA-00N row to [ledger](KEHA_P67_QA_TEST_LEDGER.md), preserving old failures.
- Verify each provider-backed result, note exact date/time if available, and update P67-0x outcome; distinguish zero results from connectivity failure.
- Update the appropriate Finnish email with *only verified* results.
- Keep key and private outbound IP out of public GitHub. The operator can insert the IP in a private reply directly to KEHA.
- Send the production request **only after** actual KEHA QA tests succeed and the scope is satisfactory to KEHA.
