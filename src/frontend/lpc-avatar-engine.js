(() => {
  "use strict";

  const BASE = "/static/assets/lpc-pack/";
  const FRAME = 64;
  const animationCycles = {
    idle: [0, 0, 1], walk: [1, 2, 3, 4, 5, 6, 7, 8], run: [0, 1, 2, 3, 4, 5, 6, 7],
    sit: [0, 0, 1, 1, 2, 2], jump: [0, 1, 2, 3, 4, 1], emote: [0, 0, 1, 1, 2, 2],
    spellcast: [0, 1, 2, 3, 4, 5, 6], thrust: [0, 1, 2, 3, 4, 5, 6, 7],
    slash: [0, 1, 2, 3, 4, 5], shoot: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    hurt: [0, 1, 2, 3, 4, 5], climb: [0, 1, 2, 3, 4, 5], combat_idle: [0, 0, 1],
    backslash: [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12], halfslash: [0, 1, 2, 3, 4, 5],
  };
  const colorFilters = {
    natural: "none", peach: "none", rose: "hue-rotate(-9deg) saturate(.92) brightness(1.02)",
    warm: "sepia(.28) saturate(1.18) brightness(.88)", deep: "sepia(.38) saturate(1.25) brightness(.62)",
    olive: "sepia(.3) hue-rotate(18deg) saturate(.9) brightness(.78)", porcelain: "saturate(.72) brightness(1.08)",
    sand: "sepia(.18) saturate(1.08) brightness(.93)", golden: "sepia(.34) saturate(1.22) brightness(.79)",
    amber: "sepia(.4) saturate(1.25) brightness(.7)", bronze: "sepia(.42) saturate(1.2) brightness(.61)",
    espresso: "sepia(.45) saturate(1.1) brightness(.45)", neutral: "sepia(.2) saturate(.95) brightness(.84)",
    brown: "hue-rotate(-18deg) saturate(.72) brightness(.66)", black: "grayscale(1) brightness(.32)",
    silver: "grayscale(1) brightness(1.42)", blue: "hue-rotate(165deg) saturate(1.3) brightness(.8)",
    teal: "hue-rotate(120deg) saturate(1.15) brightness(.82)", red: "hue-rotate(-28deg) saturate(1.25) brightness(.86)",
    orange: "none", green: "hue-rotate(66deg) saturate(1.05) brightness(.84)",
    navy: "hue-rotate(172deg) saturate(1.25) brightness(.56)", cream: "saturate(.38) brightness(1.42)",
    pink: "hue-rotate(-38deg) saturate(.82) brightness(1.18)", purple: "hue-rotate(225deg) saturate(1.15) brightness(.76)",
    white: "grayscale(1) brightness(1.7)", gray: "grayscale(1) brightness(.78)", yellow: "hue-rotate(25deg) saturate(1.4) brightness(1.2)",
  };
  const poseLabels = {
    idle: "가만히", walk: "걷기", run: "달리기", sit: "앉기", jump: "점프", emote: "기쁨 표현",
    spellcast: "반짝임 만들기", thrust: "앞으로 뻗기", slash: "힘차게 휘두르기", shoot: "멀리 가리키기",
    hurt: "깜짝 놀라기", combat_idle: "준비 자세",
  };
  const poseAnimationAliases = { fishing: "shoot", door: "thrust", dance: "emote" };
  const adaptedThrustTools = new Set(["axe", "hammer", "pickaxe"]);
  const thrustReach = [0, -1, -2, 2, 7, 7, 3, 0];
  const wateringFrames = [0, 1, 4, 4, 4, 4, 5];
  const frameCycleLengths = [...new Set([...Object.values(animationCycles).map(cycle => cycle.length),
    thrustReach.length, wateringFrames.length])];

  function actionDuration(avatar, pose) {
    if (pose === "attack") return { bow: 1280, wand: 980, cane: 860, dagger: 680 }[avatar.cosmetics?.lpcWeapon] || 780;
    if (pose === "harvest") return { axe: 1100, pickaxe: 1100, hammer: 1100, hoe: 1000, shovel: 1100, watering_can: 1400 }[avatar.cosmetics?.lpcTool] || 800;
    return null;
  }

  function cyclePosition(options, length) {
    return Number.isFinite(options.progress)
      ? Math.min(length - 1, Math.floor(Math.max(0, options.progress) * length))
      : Math.abs(Math.floor(Number(options.frame || 0))) % length;
  }

  function stableSitFrame(avatar, cycles) {
    // LPC's sit strip has three poses. Keep the field pose fully lowered and
    // use the middle pose indoors so the same toggle remains visibly distinct.
    if (avatar.sitVariant === "home") return cycles[Math.max(0, cycles.length - 3)];
    return cycles[cycles.length - 1];
  }
  const wingMobilityIds = new Set(["feathered_wings", "lizard_wings", "bat_wings", "lunar_wings"]);

  function usesWingMobility(avatar) {
    const vehicle = String(avatar.cosmetics?.vehicle || "");
    return Boolean(avatar.mounted && (wingMobilityIds.has(vehicle) || vehicle.includes("wings")));
  }

  let manifest = null;
  let assetRevision = 0;
  const items = new Map();
  const images = new Map();
  const pendingImages = new Map();
  let assetEventPending = false;

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.decoding = "async";
      image.addEventListener("load", () => resolve(image), { once: true });
      image.addEventListener("error", () => reject(new Error(`LPC image load failed: ${url}`)), { once: true });
      image.src = url;
    });
  }

  const readyPromise = fetch(`${BASE}manifest.json?v=20260901-10`)
    .then((response) => {
      if (!response.ok) throw new Error("LPC manifest load failed");
      return response.json();
    })
    .then((value) => {
      manifest = value;
      assetRevision += 1;
      value.items.forEach((item) => items.set(`${item.category}:${item.id}`, item));
      window.dispatchEvent(new CustomEvent("lpc-avatar-ready"));
      return value;
    })
    .catch((error) => {
      console.error(error);
      return null;
    });

  function item(category, id, fallback) {
    return items.get(`${category}:${id}`) || items.get(`${category}:${fallback}`);
  }

  function ensureImage(file) {
    if (!file || images.has(file) || pendingImages.has(file)) return;
    const request = loadImage(`${BASE}${file}`)
      .then((image) => {
        images.set(file, image);
        assetRevision += 1;
        if (!assetEventPending) {
          assetEventPending = true;
          requestAnimationFrame(() => {
            assetEventPending = false;
            window.dispatchEvent(new CustomEvent("lpc-avatar-assets-updated"));
          });
        }
      })
      .catch((error) => console.error(error))
      .finally(() => pendingImages.delete(file));
    pendingImages.set(file, request);
  }

  function selectedLayers(avatar, options = {}) {
    const cosmetics = avatar.cosmetics || {};
    const gender = avatar.gender === "female" ? "female" : "male";
    const bodyType = cosmetics.bodyType || gender;
    const selectedOutfit = item("outfit", cosmetics.lpcOutfit, "tshirt");
    const outfitIsOverlay = selectedOutfit?.definition?.includes("/aprons/");
    const selections = [
      ["body", "body", "body", cosmetics.skin || "peach"],
      ["bottom", cosmetics.lpcBottom, "pants", cosmetics.bottomColor || "navy"],
      ["shoes", cosmetics.lpcShoes, "shoes", cosmetics.shoeColor || "brown"],
      ...(outfitIsOverlay ? [["outfit", "tshirt", "tshirt", "white"]] : []),
      ["outfit", cosmetics.lpcOutfit, "overalls", cosmetics.outfitColor || "green"],
      ["arms", cosmetics.lpcArms, "gloves", cosmetics.outfitColor || "green"],
      ["head", cosmetics.lpcHead, gender === "female" ? "human_female" : "human_male", cosmetics.skin || "peach"],
      ["expression", cosmetics.lpcExpression, "neutral", cosmetics.skin || "peach"],
      ["nose", cosmetics.lpcNose, "button", cosmetics.skin || "peach"],
      ["eyebrow", cosmetics.lpcEyebrow, "thin", cosmetics.hairColor || "brown"],
      ["eyes", cosmetics.lpcEyes, "cyclops", "natural"],
      ["wrinkles", cosmetics.lpcWrinkles, "wrinkles", cosmetics.skin || "peach"],
      ["hair", cosmetics.lpcHair, "bob", cosmetics.hairColor || "brown"],
      ["eyewear", cosmetics.lpcGlasses, "round", cosmetics.glassesColor || "brown"],
      ["hat", cosmetics.lpcHat, "leather_cap", cosmetics.hatColor || "brown"],
    ];
    if (options.pose === "attack" && cosmetics.lpcWeapon && !["none", "wand"].includes(cosmetics.lpcWeapon)) {
      selections.push(["weapon", cosmetics.lpcWeapon, "arming_sword", "natural"]);
    }
    if (options.pose === "harvest" && cosmetics.lpcTool && cosmetics.lpcTool !== "none") {
      selections.push(["tool", cosmetics.lpcTool, "axe", "natural"]);
    }
    if ((avatar.mounted || options.previewMobility) && cosmetics.vehicle !== "none") {
      selections.push(["mobility", cosmetics.vehicle, "wheelchair", cosmetics.mobilityColor || "black"]);
    }
    const output = [];
    selections.forEach(([category, selected, fallback, color]) => {
      if (selected === "none") return;
      const record = item(category, selected, fallback);
      let layers = record?.sources?.[bodyType] || [];
      if (!layers.length && ["bottom", "shoes", "outfit", "arms", "tool", "weapon", "mobility", "hair", "eyewear", "hat"].includes(category)) {
        layers = record?.sources?.[gender] || record?.sources?.male || record?.sources?.female || [];
      }
      layers.forEach((layer) => output.push({ ...layer, color, category, item: record }));
    });
    return output.sort((left, right) => left.z - right.z);
  }

  function sharedAnimation(avatar, options, candidates) {
    const layers = selectedLayers(avatar, options);
    return candidates.find((candidate) => layers.every((layer) => (
      layer.item?.animations || []
    ).includes(candidate)));
  }

  function resolvedAnimation(avatar, options) {
    if (options.pose === "attack") {
      const weapon = avatar.cosmetics?.lpcWeapon || "none";
      // 공식 LPC 완드 시트에는 slash 레이어만 있지만, 캐릭터 본체는 spellcast 행을
      // 완전하게 지원한다. 완드는 아래 drawActionProp에서 주문 자세에 맞춰 그린다.
      if (weapon === "wand") return "spellcast";
      if (weapon === "none") return "spellcast"; // Empty-hand gesture without magic props.
      const supported = item("weapon", weapon, "arming_sword")?.animations || [];
      const preferences = {
        bow: ["shoot", "slash"],
        cane: ["thrust", "slash"],
        dagger: ["slash", "thrust", "halfslash"],
        arming_sword: ["slash", "halfslash", "backslash"],
      }[weapon] || ["slash", "thrust", "shoot", "spellcast"];
      const weaponAnimations = preferences.filter((animation) => supported.includes(animation));
      return sharedAnimation(avatar, options, weaponAnimations) || weaponAnimations[0] || "slash";
    }
    if (options.pose === "harvest") {
      return "thrust";
    }
    const requestedPose = poseAnimationAliases[options.pose] || options.pose;
    if (requestedPose && animationCycles[requestedPose]) {
      const poseFallbacks = {
        jump: ["jump", "walk", "idle"],
        emote: ["emote", "idle", "walk"],
        sit: ["sit", "idle", "walk"],
        hurt: ["hurt", "idle", "walk"],
      }[requestedPose] || [requestedPose, "idle", "walk"];
      return sharedAnimation(avatar, options, poseFallbacks) || requestedPose;
    }
    if (avatar.sitting) return sharedAnimation(avatar, options, ["sit", "idle", "walk"]) || "sit";
    if (avatar.mounted) return usesWingMobility(avatar) ? "idle" : "sit";
    if (options.moving) {
      const movementAnimations = options.running ? ["run", "walk", "idle"] : ["walk", "idle"];
      return sharedAnimation(avatar, options, movementAnimations) || "walk";
    }
    return "idle";
  }

  function drawActionProp(context, destination, direction, pose, frame, cosmetics = {}) {
    if (!pose) return;
    const scaleX = destination.width / FRAME;
    const scaleY = destination.height / FRAME;
    context.save();
    context.lineCap = "round";
    if (pose === "fishing") {
      const handX = destination.x + (direction === "left" ? 21 : 43) * scaleX;
      const handY = destination.y + 37 * scaleY;
      const endX = handX + (direction === "left" ? -24 : 24) * scaleX;
      const endY = destination.y + (22 + Math.min(frame, 6)) * scaleY;
      context.strokeStyle = "#76502f";
      context.lineWidth = Math.max(2, scaleX);
      context.beginPath(); context.moveTo(handX, handY); context.lineTo(endX, endY); context.stroke();
      context.strokeStyle = "#dbeef4";
      context.lineWidth = Math.max(1, scaleX * 0.55);
      context.beginPath(); context.moveTo(endX, endY); context.quadraticCurveTo(endX + 8 * scaleX, endY + 12 * scaleY, endX + 3 * scaleX, destination.y + 61 * scaleY); context.stroke();
      context.fillStyle = "#e85d48";
      context.fillRect(endX + 2 * scaleX, destination.y + 59 * scaleY, 2 * scaleX, 2 * scaleY);
    } else if (pose === "attack" && cosmetics.lpcWeapon === "wand") {
      const facingLeft = direction === "left";
      const wandX = direction === "up" ? 22 : facingLeft ? 18 : 44;
      const wandTop = 22 - Math.min(3, frame % 4);
      drawPixel(context, destination, wandX, wandTop + 5, 2, 15, "#6f4528");
      drawPixel(context, destination, wandX - 1, wandTop + 3, 4, 4, "#e6c27a");
      drawPixel(context, destination, wandX, wandTop + 2, 2, 2, "#fff4bc");
      const sparkleShift = frame % 3;
      drawPixel(context, destination, wandX - 5 - sparkleShift, wandTop, 2, 2, "#b991ff");
      drawPixel(context, destination, wandX + 6 + sparkleShift, wandTop + 4, 2, 2, "#75d9ff");
      drawPixel(context, destination, wandX + (facingLeft ? -7 : 8), wandTop - 4, 1, 3, "#fff4bc");
      drawPixel(context, destination, wandX + (facingLeft ? -8 : 7), wandTop - 3, 3, 1, "#fff4bc");
    } else if (pose === "door") {
      drawPixel(context, destination, direction === "left" ? 15 : 47, 34, 2, 2, "#ffe69a");
    }
    context.restore();
  }

  function drawPixel(context, destination, x, y, width, height, color) {
    const scaleX = destination.width / FRAME;
    const scaleY = destination.height / FRAME;
    context.fillStyle = color;
    context.fillRect(
      Math.round(destination.x + x * scaleX), Math.round(destination.y + y * scaleY),
      Math.max(1, Math.round(width * scaleX)), Math.max(1, Math.round(height * scaleY)),
    );
  }


  function draw(context, avatar, options = {}, destination = {}) {
    if (!manifest) return false;
    const target = { x: destination.x || 0, y: destination.y || 0, width: destination.width || 192, height: destination.height || 192 };
    const direction = ["up", "left", "down", "right"].includes(options.direction || avatar.direction)
      ? (options.direction || avatar.direction) : "down";
    const animation = resolvedAnimation(avatar, options);
    const cycles = animationCycles[animation] || animationCycles.idle;
    const frameIndex = (avatar.sitting || (avatar.mounted && !usesWingMobility(avatar))) && !options.pose
      ? stableSitFrame(avatar, cycles)
      : cycles[cyclePosition(options, cycles.length)];
    context.save();
    context.imageSmoothingEnabled = false;
    selectedLayers(avatar, options).forEach((layer) => {
      const image = images.get(layer.file);
      if (!image) { ensureImage(layer.file); return; }
      const supported = layer.item?.animations || [];
      const requestedAnimation = layer.category === "mobility" && avatar.mounted && options.moving
        ? (options.running ? "run" : "walk")
        : animation;
      const fallbackAnimations = {
        idle: ["walk"],
        walk: ["idle"],
        run: ["walk", "idle"],
        jump: ["walk", "idle"],
        sit: ["idle", "walk"],
        emote: ["idle", "walk"],
        combat_idle: ["idle", "walk"],
        spellcast: ["idle", "walk"],
        thrust: ["idle", "walk"],
        slash: ["idle", "walk"],
        shoot: ["idle", "walk"],
        hurt: ["idle", "walk"],
      };
      const layerAnimation = supported.includes(requestedAnimation)
        ? requestedAnimation
        : (fallbackAnimations[requestedAnimation] || ["idle", "walk"])
          .find((candidate) => supported.includes(candidate));
      if (!layerAnimation) return;
      const layerCycle = animationCycles[layerAnimation] || animationCycles.idle;
      const requestedFrame = requestedAnimation === "sit"
        ? frameIndex
        : ["idle", "emote", "combat_idle"].includes(requestedAnimation)
          ? layerCycle[Math.min(1, layerCycle.length - 1)]
        : layerCycle[cyclePosition(options, layerCycle.length)];
      const adaptedTool = options.pose === "harvest" && layer.category === "tool"
        && adaptedThrustTools.has(avatar.cosmetics?.lpcTool);
      // These tools have no native thrust sheet. Reuse the official held-tool
      // sprite and move it with the body's forward reach, never the overhead sheet.
      if (adaptedTool && Number(layer.frameSize || FRAME) !== FRAME) return;
      const watering = options.pose === "harvest" && avatar.cosmetics?.lpcTool === "watering_can" && layerAnimation === "thrust";
      const layerFrame = adaptedTool ? 0 : watering ? wateringFrames[cyclePosition(options, wateringFrames.length)] : requestedFrame;
      const layerRowBase = manifest.animationRows[layerAnimation] ?? manifest.animationRows.idle;
      const layerDirectionRow = layerAnimation === "hurt" || layerAnimation === "climb"
        ? 0
        : manifest.directionRows[direction];
      const layerFrameSize = Number(layer.frameSize || FRAME);
      const destinationScale = layerFrameSize / FRAME;
      const destinationWidth = target.width * destinationScale;
      const destinationHeight = target.height * destinationScale;
      const reach = adaptedTool ? thrustReach[cyclePosition(options, thrustReach.length)] : 0;
      const offset = { up: [0, -reach], down: [0, reach], left: [-reach, 0], right: [reach, 0] }[direction];
      const destinationX = target.x - (destinationWidth - target.width) / 2 + offset[0] * target.width / FRAME;
      const destinationY = target.y - (destinationHeight - target.height) / 2 + offset[1] * target.height / FRAME;
      context.save();
      context.filter = colorFilters[layer.color] || "none";
      context.drawImage(
        image,
        layerFrame * layerFrameSize,
        (layerRowBase + layerDirectionRow) * layerFrameSize,
        layerFrameSize,
        layerFrameSize,
        destinationX,
        destinationY,
        destinationWidth,
        destinationHeight,
      );
      context.restore();
    });
    drawActionProp(context, target, direction, options.pose, frameIndex, avatar.cosmetics || {});
    context.restore();
    return true;
  }

  function frameKey(avatar, options = {}) {
    if (!manifest) return null;
    // Rest/sit frames are pinned by draw(). Animated layers can have different
    // strip lengths; include each cycle position, including action-tool strips.
    const positions = !options.pose && !options.moving ? null
      : frameCycleLengths.map(length => cyclePosition(options, length));
    return JSON.stringify([assetRevision, avatar.gender, avatar.sitting, avatar.sitVariant,
      avatar.mounted, avatar.cosmetics, options.direction || avatar.direction, Boolean(options.moving),
      Boolean(options.running), options.pose || null, positions]);
  }

  function catalog(category) {
    if (category === "pose") return Object.entries(poseLabels).map(([id, label]) => ({ id, label }));
    return manifest?.items.filter((record) => record.category === category) || [];
  }

  async function prepare(avatars) {
    if (!await readyPromise) throw new Error("공식 LPC 의상 목록을 불러오지 못했어요.");
    const groups = avatars.map(avatar => {
      const layers = selectedLayers(avatar);
      const required = ["body", "head", "outfit", "bottom"];
      if (avatar.cosmetics?.lpcShoes !== "none") required.push("shoes");
      if (required.some(category => !layers.some(layer => layer.category === category && layer.file))) {
        throw new Error("공식 의상의 몸·얼굴·상의·하의 레이어가 완전하지 않아요.");
      }
      return layers;
    });
    const files = [...new Set(groups.flatMap(layers => layers.map(layer => layer.file)).filter(Boolean))];
    if (!files.length) throw new Error("촬영할 공식 의상 레이어가 없어요.");
    files.forEach(ensureImage);
    await Promise.all(files.map(file => pendingImages.get(file)).filter(Boolean));
    // draw() deliberately permits progressive loading during normal gameplay;
    // a keepsake must fail closed instead of recording partial/bare outfits.
    if (files.some(file => !images.has(file))) throw new Error("일부 공식 의상 이미지를 불러오지 못했어요. 다시 촬영해 주세요.");
    return true;
  }

  window.LpcAvatarEngine = {
    ready: () => readyPromise,
    prepare,
    isReady: () => Boolean(manifest),
    draw,
    frameKey,
    catalog,
    poseLabels,
    colors: colorFilters,
    actionDuration,
  };
})();
