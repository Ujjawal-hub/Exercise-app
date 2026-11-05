// Rhino — the page's JavaScript.
//
// How it works:
// - The part of the address after "#" says which page to show:
//     #/                  home
//     #/category/9        one category
//     #/exercise/1551     one exercise
//     #/routines/legs     warmup + cooldown for one body part
// - For each page we ask the server (/api/...) for JSON and build the page from it.
// - Data is ALWAYS put on the page with textContent (via el()), never innerHTML,
//   so text from the database can never run as code.

"use strict";

const app = document.getElementById("app");

// ------------------------------------------------------------
// Small helpers
// ------------------------------------------------------------

/** Make an element. Text goes in with textContent, so it is always shown as plain text. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

/** Only allow normal web links (http/https). A "javascript:" link in the data is refused. */
function safeUrl(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** A link. Outside links open in a new tab. Returns plain text if the URL is not safe. */
function link(text, url, outside) {
  const href = safeUrl(url);
  if (!href) return el("span", null, text);
  const a = el("a", null, text);
  a.href = href;
  if (outside) {
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  }
  return a;
}

/** A picture, or null if there is no safe URL. alt = "" when nearby text already names it. */
function picture(url, alt, className) {
  const src = safeUrl(url);
  if (!src) return null;
  const img = el("img", className);
  img.src = src;
  img.alt = alt;
  img.loading = "lazy";
  img.decoding = "async";
  return img;
}

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** Ask the server for JSON. Throws an error with .status if the answer is not OK. */
async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const error = new Error(`${url} answered ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/** Replace what is shown in <main>. */
function show(...nodes) {
  app.replaceChildren(...nodes.filter(Boolean));
}

function message(title, text) {
  const box = el("div", "message");
  box.append(el("h1", null, title));
  const p = el("p", null, text + " ");
  p.append(link("Go to the home page", "#/"));
  box.append(p);
  return box;
}

function draftNotice(what) {
  const box = el("p", "notice draft");
  box.append(el("strong", null, "Draft. "));
  box.append(`${what} not been checked against its sources yet. Compare with the source link before relying on it.`);
  return box;
}

function medicalNotice() {
  const box = el("p", "notice");
  box.append(el("strong", null, "General guidance, not medical advice. "));
  box.append("If something hurts, stop and see a doctor or physiotherapist.");
  return box;
}

// Categories are needed by the menu and the home page; load them once.
const categoriesPromise = getJSON("/api/categories").catch(() => []);

// ------------------------------------------------------------
// Cards and tiles
// ------------------------------------------------------------

/** Big photo card for an exercise with my guide. */
function guideCard(item) {
  const card = el("a", "card");
  card.href = `#/exercise/${item.id}`;
  const img = picture(item.thumbnail, "");
  if (img) card.append(img);
  if (item.guide && !item.guide.reviewed) card.append(el("span", "badge", "Draft"));
  const text = el("div", "card-text");
  if (item.category) text.append(el("p", "card-caption", item.category));
  text.append(el("h3", "card-title", item.name));
  card.append(text);
  return card;
}

/** Small tile for an exercise without a guide. */
function exerciseTile(item) {
  const li = el("li");
  const tile = el("a", "tile");
  tile.href = `#/exercise/${item.id}`;
  tile.append(picture(item.thumbnail, "", "thumb") || el("span", "thumb"));
  tile.append(el("span", null, item.name));
  li.append(tile);
  return li;
}

// ------------------------------------------------------------
// Pages
// ------------------------------------------------------------

async function homePage(isCurrent) {
  const [guides, categories] = await Promise.all([getJSON("/api/guides"), categoriesPromise]);
  if (!isCurrent()) return;
  document.title = "Rhino — exercise form guides";

  const hero = el("section", "hero");
  const heroInner = el("div", "hero-inner");
  const h1 = el("h1");
  h1.append(el("span", null, "Form first."), el("span", null, "Weight second."));
  heroInner.append(h1, el("p", null, "Step-by-step form guides, common mistakes, and how to fix them."));
  hero.append(heroInner);

  // One section per category, in the same order as the menu.
  const sections = [];
  for (const category of categories) {
    const items = guides.filter((g) => g.category === category.name);
    if (!items.length) continue;
    const section = el("section", "section wrap");
    const head = el("div", "section-head");
    head.append(el("h2", null, category.name));
    head.append(link(`All ${plural(category.exercise_count, "exercise")} in ${category.name}`,
                     `#/category/${category.id}`));
    const cards = el("div", "cards");
    items.forEach((item) => cards.append(guideCard(item)));
    section.append(head, cards);
    sections.push(section);
  }
  show(hero, ...sections);
}

async function categoryPage(isCurrent, categoryId) {
  const data = await getJSON(`/api/categories/${categoryId}/exercises`);
  if (!isCurrent()) return;
  document.title = `${data.category.name} — Rhino`;

  const head = el("header", "page-head wrap");
  head.append(el("h1", null, data.category.name));
  head.append(el("p", null,
    `${plural(data.guides.length, "form guide")} and ${plural(data.total_others, "other exercise")}.`));

  const nodes = [head];
  if (data.guides.length) {
    const section = el("section", "section wrap");
    const sectionHead = el("div", "section-head");
    sectionHead.append(el("h2", null, "Form guides"));
    const cards = el("div", "cards");
    data.guides.forEach((item) => cards.append(guideCard(item)));
    section.append(sectionHead, cards);
    nodes.push(section);
  }

  if (data.total_others) {
    const section = el("section", "section wrap");
    const sectionHead = el("div", "section-head");
    sectionHead.append(el("h2", null, "Other exercises"));
    sectionHead.append(el("p", "quiet", "No form guide written yet. Shown with wger's information."));
    const tiles = el("ul", "tiles");
    data.others.forEach((item) => tiles.append(exerciseTile(item)));
    section.append(sectionHead, tiles);

    // "Show more" asks the server for the next 50 and adds them to the list.
    let nextOffset = data.next_offset;
    if (nextOffset !== null) {
      const more = el("button", "more", "Show more exercises");
      more.type = "button";
      more.addEventListener("click", async () => {
        more.disabled = true;
        more.textContent = "Loading…";
        try {
          const page = await getJSON(`/api/categories/${categoryId}/exercises?offset=${nextOffset}`);
          page.others.forEach((item) => tiles.append(exerciseTile(item)));
          nextOffset = page.next_offset;
          if (nextOffset === null) more.remove();
          else more.textContent = "Show more exercises";
        } catch {
          more.textContent = "Couldn't load more. Try again";
        }
        more.disabled = false;
      });
      section.append(more);
    }
    nodes.push(section);
  }
  show(...nodes);
}

async function exercisePage(isCurrent, exerciseId) {
  let ex;
  try {
    ex = await getJSON(`/api/exercises/${exerciseId}`);
  } catch (error) {
    if (error.status === 404) {
      if (isCurrent()) show(message("Exercise not found", "There is no exercise with this number."));
      return;
    }
    throw error;
  }
  if (!isCurrent()) return;
  document.title = `${ex.name} — Rhino`;
  const guide = ex.guide;
  const categories = await categoriesPromise;
  const category = categories.find((c) => c.name === ex.category);

  // --- Top: photo + name + notices ---
  const top = el("section", "ex-top wrap");
  const media = el("div", "ex-media");
  const photo = el("div", "ex-photo");
  const firstImage = ex.images[0] ? picture(ex.images[0].url, ex.name) : null;
  if (firstImage) photo.append(firstImage);
  media.append(photo);
  if (ex.images.length > 1) {
    // Small pictures under the big one; clicking one shows it big.
    const strip = el("div", "ex-strip");
    ex.images.forEach((image, index) => {
      const small = picture(image.url, `Picture ${index + 1} of ${ex.name}`);
      if (!small) return;
      const button = el("button");
      button.type = "button";
      button.setAttribute("aria-pressed", index === 0 ? "true" : "false");
      button.append(small);
      button.addEventListener("click", () => {
        const big = picture(image.url, ex.name);
        if (big) photo.replaceChildren(big);
        strip.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
        button.setAttribute("aria-pressed", "true");
      });
      strip.append(button);
    });
    media.append(strip);
  }

  const head = el("div", "ex-head");
  if (category) {
    const p = el("p", "ex-category");
    p.append(link(category.name, `#/category/${category.id}`));
    head.append(p);
  }
  head.append(el("h1", null, ex.name));
  if (ex.wger_name && ex.wger_name !== ex.name) {
    head.append(el("p", "ex-alias", `Called "${ex.wger_name}" on wger.`));
  }
  if (guide && !guide.reviewed) head.append(draftNotice("This form guide has"));
  if (ex.credit.type === "custom" && !ex.credit.reviewed) {
    head.append(draftNotice("The muscle and equipment list for this exercise has"));
  }
  head.append(medicalNotice());
  if (firstImage) {
    top.append(media, head);
  } else {
    top.classList.add("no-photo"); // no picture at all: don't show an empty grey box
    top.append(head);
  }

  // --- Main column: the guide, or wger's description ---
  const main = el("div", "ex-main");
  if (guide) {
    const setup = el("section", "detail");
    setup.append(el("h2", null, "Setup"), el("p", null, guide.setup));
    main.append(setup);

    const steps = el("section", "detail");
    steps.append(el("h2", null, "How to do it"));
    const list = el("ol", "steps");
    guide.steps.forEach((text) => list.append(el("li", null, text)));
    steps.append(list);
    main.append(steps);

    if (guide.mistakes.length) {
      const mistakes = el("section", "detail");
      mistakes.append(el("h2", null, "Common mistakes"));
      const mlist = el("ul", "mistakes");
      guide.mistakes.forEach((m) => {
        const li = el("li");
        li.append(el("p", "mistake", m.mistake));
        const fix = el("p", "fix");
        fix.append(el("span", "fix-label", "Fix: "), m.fix);
        li.append(fix);
        mlist.append(li);
      });
      mistakes.append(mlist);
      main.append(mistakes);
    }

    if (guide.form_images.length) {
      const pics = el("section");
      pics.append(el("h2", null, "Form pictures"));
      const grid = el("div", "form-pictures");
      guide.form_images.forEach((url, index) => {
        const img = picture(url, `${guide.name}: form picture ${index + 1}`);
        if (!img) return;
        const a = link("", url, true);
        a.append(img);
        grid.append(a);
      });
      pics.append(grid);
      main.append(pics);
    }

    if (safeUrl(guide.demo_url)) {
      const demo = el("section");
      demo.append(el("h2", null, "Watch it done"));
      const button = link("Watch the demo on YouTube", guide.demo_url, true);
      button.className = "button";
      demo.append(button);
      main.append(demo);
    }
  } else {
    const none = el("section");
    none.append(el("h2", null, "Form guide not written yet"));
    if (ex.description) {
      none.append(el("p", "quiet", "Here is the description from wger in the meantime."));
      const prose = el("div", "prose");
      ex.description.split("\n").forEach((line) => prose.append(el("p", null, line)));
      prose.firstChild.style.marginTop = "14px";
      none.append(prose);
    } else {
      none.append(el("p", "quiet", "wger has no description for this exercise either."));
    }
    main.append(none);
  }

  // --- Side column: muscles, equipment, sources and credits ---
  const side = el("aside", "ex-side");
  const feel = el("section", "detail");
  feel.append(el("h2", null, "What you should feel"));
  if (ex.muscles.primary.length || ex.muscles.secondary.length) {
    if (ex.muscles.primary.length) {
      feel.append(el("h3", null, "Main muscles"), el("p", null, ex.muscles.primary.join(", ")));
    }
    if (ex.muscles.secondary.length) {
      feel.append(el("h3", null, "Also working"), el("p", null, ex.muscles.secondary.join(", ")));
    }
  } else {
    feel.append(el("p", "quiet", "Muscles not listed for this exercise."));
  }
  feel.append(el("h3", null, "Equipment"));
  feel.append(el("p", null, ex.equipment.length ? ex.equipment.join(", ") : "Not listed"));
  side.append(feel);

  const sources = el("section");
  sources.append(el("h2", null, "Sources"));
  if (guide) {
    const p = el("p", null, "Form guide: ");
    p.append(link(guide.source_name, guide.source_url, true));
    sources.append(p);
  }
  if (ex.credit.type === "custom") {
    const p = el("p", null, "Exercise details: ");
    p.append(link(ex.credit.source_name, ex.credit.source_url, true));
    sources.append(p);
  } else {
    const p = el("p", null, "Exercise details from ");
    p.append(link("wger", ex.credit.site_url, true));
    if (ex.credit.author) p.append(`, by ${ex.credit.author}`);
    if (ex.credit.license_name) {
      p.append(", licensed ");
      p.append(link(ex.credit.license_name, ex.credit.license_url, true));
    }
    p.append(".");
    sources.append(p);
  }
  const photoAuthors = [...new Set(ex.images.filter((i) => i.from_wger && i.author).map((i) => i.author))];
  if (photoAuthors.length) {
    sources.append(el("p", "quiet", `Photos from wger by ${photoAuthors.join(", ")}.`));
  }
  side.append(sources);

  const body = el("div", "ex-body wrap");
  body.append(main, side);
  show(top, body);
}

async function routinePage(isCurrent, bodyPart) {
  let data;
  try {
    data = await getJSON(`/api/routines/${encodeURIComponent(bodyPart)}`);
  } catch (error) {
    if (error.status === 404) {
      if (isCurrent()) show(message("Routine not found", "There is no warmup or cooldown for this body part."));
      return;
    }
    throw error;
  }
  if (!isCurrent()) return;
  const name = capitalize(data.body_part);
  document.title = `${name} warmup and cooldown — Rhino`;

  const head = el("header", "page-head wrap");
  head.append(el("h1", null, name));
  head.append(el("p", null, "Warm up before you train, cool down after. Skipping them is a common cause of injury."));
  head.append(medicalNotice());

  const grid = el("div", "routine-grid wrap");
  for (const [title, routine] of [["Warmup", data.warmup], ["Cooldown", data.cooldown]]) {
    if (!routine) continue;
    const box = el("section", "routine");
    box.append(el("h2", null, title));
    if (!routine.reviewed) box.append(draftNotice("This routine has"));
    const list = el("ol", "steps");
    routine.steps.forEach((step) => {
      const li = el("li", null, step.instruction);
      if (step.amount) li.append(el("span", "amount", step.amount));
      list.append(li);
    });
    box.append(list);
    const source = el("p", "source quiet", "Source: ");
    source.append(link(routine.source_name, routine.source_url, true));
    box.append(source);
    grid.append(box);
  }
  show(head, grid);
}

// ------------------------------------------------------------
// Router: pick the page from the address
// ------------------------------------------------------------

const routes = [
  [/^#?\/?$/, homePage],
  [/^#\/category\/(\d+)$/, categoryPage],
  [/^#\/exercise\/(\d+)$/, exercisePage],
  [/^#\/routines\/([a-z-]+)$/, routinePage],
];

let pageNumber = 0; // goes up on every page change, so a slow old answer is ignored

async function router() {
  const thisPage = ++pageNumber;
  const isCurrent = () => thisPage === pageNumber;
  closeMenus();
  closeNav();
  hideResults();
  show(el("p", "status", "Loading…"));
  window.scrollTo(0, 0);

  const hash = window.location.hash;
  for (const [pattern, page] of routes) {
    const match = hash.match(pattern);
    if (!match) continue;
    try {
      await page(isCurrent, match[1]);
    } catch {
      if (isCurrent()) {
        show(message("This page couldn't load",
          "The server didn't answer. Check that it is running, then reload the page."));
      }
    }
    return;
  }
  document.title = "Page not found — Rhino";
  show(message("Page not found", "This address doesn't match any page."));
}

// ------------------------------------------------------------
// Top bar: menus, phone menu button, search
// ------------------------------------------------------------

const topbar = document.querySelector(".topbar");
const navToggle = document.querySelector(".nav-toggle");
const menus = [...document.querySelectorAll(".menu")];

function setMenu(menu, open) {
  menu.classList.toggle("open", open);
  menu.querySelector(".menu-button").setAttribute("aria-expanded", String(open));
}

function closeMenus(except) {
  menus.forEach((menu) => { if (menu !== except) setMenu(menu, false); });
}

function closeNav() {
  topbar.classList.remove("nav-open");
  navToggle.setAttribute("aria-expanded", "false");
}

menus.forEach((menu) => {
  const button = menu.querySelector(".menu-button");
  button.addEventListener("click", () => {
    const open = !menu.classList.contains("open");
    closeMenus(menu);
    setMenu(menu, open);
    if (open) hideResults();
  });
});

navToggle.addEventListener("click", () => {
  const open = !topbar.classList.contains("nav-open");
  topbar.classList.toggle("nav-open", open);
  navToggle.setAttribute("aria-expanded", String(open));
});

function menuItem(text, count, href) {
  const li = el("li");
  const a = el("a");
  a.href = href;
  a.append(el("span", null, text));
  if (count) a.append(el("span", "menu-count", count));
  li.append(a);
  return li;
}

async function fillMenus() {
  const exercisesMenu = document.getElementById("menu-exercises");
  const routinesMenu = document.getElementById("menu-routines");
  const categories = await categoriesPromise;
  categories.forEach((c) => {
    const count = c.guide_count ? plural(c.guide_count, "guide") : "";
    exercisesMenu.append(menuItem(c.name, count, `#/category/${c.id}`));
  });
  try {
    const routines = await getJSON("/api/routines");
    routines.forEach((r) => routinesMenu.append(menuItem(capitalize(r.body_part), "", `#/routines/${r.body_part}`)));
  } catch {
    routinesMenu.append(el("li", "search-empty", "Couldn't load routines."));
  }
}

const searchInput = document.getElementById("search-input");
const searchResults = document.getElementById("search-results");
let searchTimer = null;
let searchNumber = 0; // same idea as pageNumber: ignore answers to old searches

function hideResults() {
  searchResults.hidden = true;
}

function resultLinks() {
  return [...searchResults.querySelectorAll("a")];
}

async function runSearch() {
  const query = searchInput.value.trim();
  const thisSearch = ++searchNumber;
  if (query.length < 2) {
    hideResults();
    return;
  }
  let items;
  try {
    items = await getJSON(`/api/search?q=${encodeURIComponent(query)}`);
  } catch {
    items = null;
  }
  if (thisSearch !== searchNumber) return;

  searchResults.replaceChildren();
  if (items === null) {
    searchResults.append(el("li", "search-empty", "Search isn't working right now. Try again."));
  } else if (!items.length) {
    searchResults.append(el("li", "search-empty", `No exercises match "${query}".`));
  } else {
    items.forEach((item) => {
      const li = el("li");
      const a = el("a");
      a.href = `#/exercise/${item.id}`;
      a.append(picture(item.thumbnail, "", "thumb") || el("span", "thumb"));
      const text = el("span");
      text.append(el("span", "result-name", item.name));
      const meta = [item.category, item.guide ? (item.guide.reviewed ? "Form guide" : "Form guide, draft") : null]
        .filter(Boolean).join(", ");
      text.append(el("span", "result-meta", meta));
      text.firstChild.style.display = "block";
      a.append(text);
      a.addEventListener("click", () => { searchInput.value = ""; hideResults(); });
      li.append(a);
      searchResults.append(li);
    });
  }
  closeMenus();
  searchResults.hidden = false;
}

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 200); // wait until typing pauses
});

searchInput.addEventListener("keydown", (event) => {
  const links = resultLinks();
  if (event.key === "ArrowDown" && links.length && !searchResults.hidden) {
    event.preventDefault();
    links[0].focus();
  } else if (event.key === "Enter" && links.length && !searchResults.hidden) {
    event.preventDefault();
    links[0].click();
  }
});

searchResults.addEventListener("keydown", (event) => {
  const links = resultLinks();
  const index = links.indexOf(document.activeElement);
  if (event.key === "ArrowDown" && index < links.length - 1) {
    event.preventDefault();
    links[index + 1].focus();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (index > 0) links[index - 1].focus();
    else searchInput.focus();
  }
});

// Click anywhere else: close menus and search results.
document.addEventListener("click", (event) => {
  if (!event.target.closest(".menu")) closeMenus();
  if (!event.target.closest(".search")) hideResults();
});

// Escape closes whatever is open.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const openMenu = menus.find((m) => m.classList.contains("open"));
  closeMenus();
  if (openMenu) openMenu.querySelector(".menu-button").focus();
  if (!searchResults.hidden) {
    hideResults();
    searchInput.focus();
  }
});

// ------------------------------------------------------------
// Start
// ------------------------------------------------------------

// "Skip to content" must not change the address (that would open "Page not found").
document.querySelector(".skip-link").addEventListener("click", (event) => {
  event.preventDefault();
  app.focus();
});

window.addEventListener("hashchange", router);
fillMenus();
router();
