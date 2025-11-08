// /static/js/utils.js

export async function loadPeople() {
    let people = JSON.parse(localStorage.getItem("people"));

    if (!people) {
        try {
            const res = await fetch("/people_data");
            people = await res.json();
            localStorage.setItem("people", JSON.stringify(people));
        } catch (err) {
            console.error("Failed to fetch people:", err);
        }
    }

    return people;
}

window.loadPeople = loadPeople;
