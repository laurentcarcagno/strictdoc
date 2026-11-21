// The search of the catalog of projects: it hides the projects whose name does
// not contain the text, and the folders left without a project.
(function () {
  "use strict";

  var searchInput = document.getElementById("catalog-search");
  var tree = document.getElementById("catalog-tree");
  var noMatch = document.getElementById("catalog-no-match");
  if (searchInput === null || tree === null) {
    return;
  }

  function filterFolder(folderItem) {
    var visibleProjects = folderItem.querySelectorAll(
      ".catalog__project:not([hidden])"
    ).length;
    folderItem.hidden = visibleProjects === 0;
    return visibleProjects > 0;
  }

  function filter() {
    var query = searchInput.value.trim().toLowerCase();
    var projectItems = tree.querySelectorAll(".catalog__project");
    var matchCount = 0;
    projectItems.forEach(function (projectItem) {
      var name = projectItem.getAttribute("data-name") || "";
      var isMatch = name.indexOf(query) !== -1;
      projectItem.hidden = !isMatch;
      if (isMatch) {
        matchCount += 1;
      }
    });
    tree.querySelectorAll(".catalog__folder").forEach(function (folderItem) {
      if (filterFolder(folderItem) && query !== "") {
        // A search shows its result: the folders that hold it are open.
        folderItem.querySelector("details").open = true;
      }
    });
    noMatch.hidden = matchCount > 0;
  }

  searchInput.addEventListener("input", filter);
  // The button that clears a search field fires this event.
  searchInput.addEventListener("search", filter);
})();
