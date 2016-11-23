package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationTopoguideAdvancedSearch extends Simulation {

  val httpProtocol = http
    .inferHtmlResources(C2corgConf.black_list, WhiteList())
    .acceptHeader("*/*")
    .acceptEncodingHeader("gzip, deflate")

  val scn = scenario("ConsultationTopoguideAdvancedSearch")
    .exec(Homepage.init)
    .pause(4)
    .exec(Route.advancedSearchInit)
    .pause(5)
    .exec(Route.advancedSearch)
    .pause(5)
    .exec(Route.view)

  val numUsers = Integer.getInteger("users", 100)
  val rampSec = Integer.getInteger("ramp", 300)

  setUp(scn.inject(rampUsers(numUsers) over (rampSec seconds))).protocols(httpProtocol)

}
