package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._

object Route {
  val view = exec(http("View route")
    .get("/routes/201060/fr/bel-oiseau-couloir-sse")
    .headers(C2corgConf.header_html)
    .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )
}
