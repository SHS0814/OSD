package kr.ac.cbnu.campusshade

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BuildingSearchTest {
    private fun b(fullName: String) = BuildingSearch.parse(fullName, 0.0, 0.0)!!

    private val buildings = listOf(
        "경영대학 본관 (N13)", "대학본부 (N10)", "법학전문대학원 (N2)", "산학협력관 (N4)",
        "중앙도서관 구관 (N12)", "중앙도서관 신관 (N12)", "자연대 6호관 (S1-6)", "자연대 5호관 (S1-5)",
        "자연대 4호관 (S1-4)", "중앙연구소(S19)", "전산정보원 (S2)", "공학관 (E8-1)", "제5 공학관 (E8-10)",
        "개신문화관 (E2)", "임상연구동 (H3)", "승리관", "과학기술도서관 (S1-7)",
    ).map(::b)

    @Test fun parsesNumberAndName() {
        assertEquals(Building("N13", "경영대학 본관", 0.0, 0.0), b("경영대학 본관 (N13)"))
        assertEquals("S19", b("중앙연구소(S19)").number)
        assertEquals("중앙연구소", b("중앙연구소(S19)").name)
        assertEquals("S1-6", b("자연대 6호관 (S1-6)").number)
        assertNull(b("승리관").number)
        assertEquals("N13 경영대학 본관", b("경영대학 본관 (N13)").label)
        assertEquals("승리관", b("승리관").label)
    }

    @Test fun skipsUnnamedOsmBuildings() {
        assertNull(BuildingSearch.parse("OSM way 442760295", 0.0, 0.0))
        assertNull(BuildingSearch.parse("  ", 0.0, 0.0))
    }

    @Test fun zones() {
        assertEquals("N", b("경영대학 본관 (N13)").zone)
        assertEquals("S", b("자연대 6호관 (S1-6)").zone)
        assertEquals("E", b("공학관 (E8-1)").zone)
        assertEquals(BuildingSearch.OTHER, b("임상연구동 (H3)").zone)
        assertEquals(BuildingSearch.OTHER, b("승리관").zone)
    }

    @Test fun normalizesQueries() {
        listOf("n-13", "N 13", "n13", " N13 ").forEach { assertEquals("N13", BuildingSearch.normalize(it)) }
        assertEquals("S1-6", BuildingSearch.normalize("s1-6"))
        assertEquals("S1-6", BuildingSearch.normalize("S-1-6"))
    }

    @Test fun naturalNumberOrder() {
        val numbers = listOf("N10", "N2", "S1-10", "S2", "N13", "S1-5", "S1-4", "E8-10", "E8-1", "H3", "E2")
            .sortedWith(BuildingSearch::compareNumbers)
        assertEquals(listOf("N2", "N10", "N13", "S1-4", "S1-5", "S1-10", "S2", "E2", "E8-1", "E8-10", "H3"), numbers)
    }

    @Test fun zoneListIsInNumberOrder() {
        val labels = BuildingSearch.search(buildings, "", "N").map { it.number }
        assertEquals(listOf("N2", "N4", "N10", "N12", "N12", "N13"), labels)
        assertEquals(listOf("S1-4", "S1-5", "S1-6", "S1-7", "S2", "S19"), BuildingSearch.search(buildings, "", "S").map { it.number })
        assertEquals(listOf("H3", null), BuildingSearch.search(buildings, "", BuildingSearch.OTHER).map { it.number })
    }

    @Test fun allListPutsUnnumberedLast() {
        val all = BuildingSearch.search(buildings, "")
        assertEquals("N2", all.first().number)
        assertEquals("승리관", all.last().name)
    }

    @Test fun numberPrefixAndExactFirst() {
        val result = BuildingSearch.search(buildings, "n1").map { it.number }
        assertEquals(listOf("N10", "N12", "N12", "N13"), result)
        assertEquals("N13", BuildingSearch.search(buildings, "N-13").first().number)
        assertEquals(listOf("S1-4", "S1-5", "S1-6", "S1-7", "S19"), BuildingSearch.search(buildings, "s1").map { it.number })
        assertEquals(listOf("S2"), BuildingSearch.search(buildings, "S2").map { it.number })
    }

    @Test fun exactNumberBeatsPrefix() {
        val list = listOf(b("가 (N10)"), b("나 (N1)"))
        assertEquals(listOf("N1", "N10"), BuildingSearch.search(list, "N1").map { it.number })
    }

    @Test fun namePartialMatch() {
        val result = BuildingSearch.search(buildings, "도서관").map { it.label }
        assertEquals(listOf("N12 중앙도서관 구관", "N12 중앙도서관 신관", "S1-7 과학기술도서관"), result)
        assertEquals(listOf("승리관"), BuildingSearch.search(buildings, "승리").map { it.label })
        // A name starting with the query comes before one only containing it.
        assertEquals(listOf("E8-1", "E8-10"), BuildingSearch.search(buildings, "공학관").map { it.number })
    }

    @Test fun labelSearchFindsPickedBuilding() {
        assertEquals("N13", BuildingSearch.search(buildings, "N13 경영대학 본관").single().number)
    }

    @Test fun zoneFilterAppliesToQuery() {
        assertEquals(emptyList<String?>(), BuildingSearch.search(buildings, "N13", "S").map { it.number })
        assertEquals(listOf("S1-7"), BuildingSearch.search(buildings, "도서관", "S").map { it.number })
    }
}
