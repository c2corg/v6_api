package c2corg

import io.gatling.core.Predef._

object C2corgConf {
  val ui_url = "http://www.demov6.camptocamp.org"
  val api_url = "http://api.demov6.camptocamp.org"
  val forum_url = "http://forum.demov6.camptocamp.org"

  val header_json = Map(
      "Accept" -> "application/json",
      "Origin" -> ui_url)

  val header_html = Map("Accept" -> "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

  val basic_auth_username = "c2corg"
  val basic_auth_password = "c2corg"

  val black_list = BlackList("""http://server1.affiz.net/.*""", """https://www.google-analytics.com/analytics.js""", """http://sos.exo.io/.*""", """.*/static/.*""", """.*/images/proxy/.*""")
}
