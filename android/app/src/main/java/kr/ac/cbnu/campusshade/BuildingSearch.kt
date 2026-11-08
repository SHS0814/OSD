package kr.ac.cbnu.campusshade

import java.util.Locale

/**
 * A campus building for search: its number such as "N13" or "S1-6" (null when the
 * building has none) and its name without the number.
 */
data class Building(val number: String?, val name: String, val latitude: Double, val longitude: Double) {
    /** "N13 경영대학 본관", or just the name for a building without a number. */
    val label: String get() = if (number == null) name else "$number $name"
    val zone: String get() = BuildingSearch.zoneOf(number)
}

/** Building numbers, zones and search. Pure Kotlin so it can be unit tested. */
object BuildingSearch {
    const val ALL = "전체"
    const val OTHER = "기타"
    /** Zone chips in display order. */
    val ZONES = listOf(ALL, "N", "S", "E", OTHER)
    private val MAIN_ZONES = setOf("N", "S", "E")
    // Order of the zone letters when every building is listed; others come after.
    private const val LETTER_ORDER = "NSEH"

    // '경영대학 본관 (N13)', '자연대 6호관 (S1-6)', '중앙연구소(S19)'
    private val NUMBER = Regex("""\(\s*([NSEH]\d+(?:-\d+)*)\s*\)""")
    // Buildings OpenStreetMap has no name for.
    private val UNNAMED = Regex("""^OSM (?:way|relation|node) \d+$""")
    private val SPACES = Regex("""\s+""")
    private val HYPHEN_AFTER_LETTER = Regex("""(?<=\p{L})-""")

    /** The building named [fullName] in /api/buildings, or null for an unnamed one. */
    fun parse(fullName: String, latitude: Double, longitude: Double): Building? {
        val trimmed = fullName.trim()
        if (trimmed.isEmpty() || UNNAMED.matches(trimmed)) return null
        val match = NUMBER.find(trimmed)
        val number = match?.groupValues?.get(1)
        val name = if (match == null) trimmed else trimmed.removeRange(match.range).replace(SPACES, " ").trim()
        return Building(number, name.ifEmpty { number.orEmpty() }, latitude, longitude)
    }

    /** "N", "S" or "E" from the number's letter; [OTHER] for anything else or no number. */
    fun zoneOf(number: String?): String {
        val letter = number?.take(1)
        return if (letter != null && letter in MAIN_ZONES) letter else OTHER
    }

    /** Upper case without spaces, and without a hyphen right after a letter: "n-13", "N 13" → "N13". */
    fun normalize(text: String): String =
        text.uppercase(Locale.ROOT).replace(SPACES, "").replace(HYPHEN_AFTER_LETTER, "")

    /** Natural order of building numbers: N1 < N2 < N10, S1-4 < S1-5 < S1-10 < S2. */
    fun compareNumbers(a: String, b: String): Int {
        val (letterA, partsA) = numberParts(a)
        val (letterB, partsB) = numberParts(b)
        if (letterA != letterB) {
            val rankA = LETTER_ORDER.indexOf(letterA).let { if (it < 0) LETTER_ORDER.length else it }
            val rankB = LETTER_ORDER.indexOf(letterB).let { if (it < 0) LETTER_ORDER.length else it }
            return if (rankA != rankB) rankA.compareTo(rankB) else letterA.compareTo(letterB)
        }
        for (i in 0 until minOf(partsA.size, partsB.size)) {
            if (partsA[i] != partsB[i]) return partsA[i].compareTo(partsB[i])
        }
        return partsA.size.compareTo(partsB.size)
    }

    private fun numberParts(number: String): Pair<String, List<Int>> {
        val letter = number.takeWhile { it.isLetter() }
        return letter to number.drop(letter.length).split('-').mapNotNull { it.toIntOrNull() }
    }

    /** Numbered buildings in natural number order, then the rest by name. */
    val byNumber: Comparator<Building> = Comparator { a, b ->
        val numberA = a.number
        val numberB = b.number
        val order = when {
            numberA == null && numberB == null -> 0
            numberA == null -> 1
            numberB == null -> -1
            else -> compareNumbers(numberA, numberB)
        }
        if (order != 0) order else a.name.compareTo(b.name)
    }

    /**
     * The buildings in [zone] matching [query], best first: an exact number, then a
     * number starting with the query, then names. An empty query lists the whole zone.
     */
    fun search(buildings: List<Building>, query: String, zone: String = ALL): List<Building> {
        val inZone = if (zone == ALL) buildings else buildings.filter { it.zone == zone }
        val key = normalize(query)
        if (key.isEmpty()) return inZone.sortedWith(byNumber)
        return inZone
            .mapNotNull { building -> rank(building, key)?.let { it to building } }
            .sortedWith(compareBy<Pair<Int, Building>> { it.first }.thenComparator { x, y -> byNumber.compare(x.second, y.second) })
            .map { it.second }
    }

    private fun rank(building: Building, key: String): Int? {
        val number = building.number?.let(::normalize)
        val name = normalize(building.name)
        return when {
            number == key -> 0
            number != null && number.startsWith(key) -> 1
            // The label shown after picking a result, e.g. "N13 경영대학 본관".
            number != null && (number + name).startsWith(key) -> 1
            name.startsWith(key) -> 2
            name.contains(key) -> 3
            else -> null
        }
    }
}
